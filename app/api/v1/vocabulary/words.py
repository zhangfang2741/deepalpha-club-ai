# app/api/v1/vocabulary/words.py
"""WordLens 拍照识别 + 生词库 + 复习 API。

不用 `from __future__ import annotations`：`recognize` 挂了 slowapi 的
@limiter.limit() 装饰器，它会让 FastAPI 把 body/表单参数的类型注解解析成未展开
的 ForwardRef，导致参数被误判成 query 参数（详见 app/api/v1/vocabulary/auth.py
顶部同样的说明）。
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import suppress
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    RecognizedWordSchema,
    RecognizeResponse,
    RecognizeStreamEvent,
    ReviewQueueResponse,
    ReviewSubmitRequest,
    ReviewSubmitResponse,
    VocabularyStatsResponse,
    VocabularyWordListResponse,
    VocabularyWordResponse,
    WordsBatchCreateRequest,
    WordsBatchCreateResponse,
)
from app.services.vocabulary import words as word_service
from app.services.vocabulary.recognizer import (
    RecognitionFailedError,
    RecognizedWord,
    recognize_words_from_image,
)
from app.services.vocabulary.tts import (
    TTSNotConfiguredError,
    TTSSynthesisError,
    synthesize_speech,
)

from .dependencies import get_current_vocab_user

router = APIRouter()

# 实测 Railway 边缘代理对请求体有约 1MB 的硬限制：超过会在到达这里之前就被
# 拒绝，返回一个我们的错误处理捕获不到的裸 500（700KB 能过，900KB 必 500）。
# 这个校验对走边缘代理的正常请求基本不会触发——iOS 端拍完照会先压缩到
# 850KB 再上传（见 CameraCaptureView.compressedJPEGData），正常用户操作
# 永远碰不到这个上限。保留它只为给绕过 iOS 客户端、用 curl/Postman 直发大图的
# 调用方一个清晰的日志入口，对正常用户透明。
#
# 上限压到 900KB 而不是早先的 800KB：iOS 端 maxBytes=850KB 之后 multipart
# boundary ~5-10KB，加上表单其它字段（ocr_words 等），整 body 仍在 1MB
# 边缘代理硬限制之下. 余量更宽, 偶尔重压缩质量稍微跑偏也不会被拒.
_MAX_IMAGE_BYTES = 900 * 1024  # 900KB，对齐边缘代理约 1MB 的硬限制
_RECOGNIZE_HEARTBEAT_SECONDS = 5.0


def _build_recognize_response(recognized: list[RecognizedWord], existing_words: set[str]) -> RecognizeResponse:
    """把识别服务结果转换成 API 响应，并标记已存在的生词。"""
    new_words = word_service.filter_new_words(existing_words, [w.word for w in recognized])
    new_words_lower = {w.lower() for w in new_words}
    candidates = [
        RecognizedWordSchema(
            word=w.word,
            phonetic_ipa=w.phonetic_ipa,
            part_of_speech=w.part_of_speech,
            definition_zh=w.definition_zh,
            etymology=w.etymology,
            example_sentence=w.example_sentence,
            already_in_library=w.word.lower() not in new_words_lower,
        )
        for w in recognized
    ]
    return RecognizeResponse(candidates=candidates)


async def _stream_recognition_events(
    recognition_factory: Callable[
        [Callable[[list[RecognizedWord]], None]], Coroutine[Any, Any, list[RecognizedWord]]
    ],
    existing_words: set[str],
    heartbeat_interval: float = _RECOGNIZE_HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """在识别任务运行期间输出 NDJSON 心跳 + partial 进度，完成后输出最终结果。

    recognition_factory 接收一个 on_partial 回调、返回真正的识别 coroutine——
    这个回调把每次进度快照塞进本函数持有的队列（`partial_queue`），本函数
    一边跟原来一样等心跳超时、一边用 `asyncio.wait` 顺带消费队列，一有新快照
    就立刻转发成 partial 事件，不用等到识别 + 漏词重试全部跑完。
    """
    partial_queue: asyncio.Queue[list[RecognizedWord]] = asyncio.Queue()
    task = asyncio.create_task(recognition_factory(partial_queue.put_nowait))
    try:
        yield RecognizeStreamEvent(type="heartbeat", stage="recognizing").model_dump_json(exclude_none=True) + "\n"

        while not task.done():
            get_task = asyncio.ensure_future(partial_queue.get())
            done, _pending = await asyncio.wait(
                {task, get_task}, timeout=heartbeat_interval, return_when=asyncio.FIRST_COMPLETED
            )
            if get_task in done:
                yield (
                    RecognizeStreamEvent(
                        type="partial", data=_build_recognize_response(get_task.result(), existing_words)
                    ).model_dump_json(exclude_none=True)
                    + "\n"
                )
                continue
            get_task.cancel()
            with suppress(asyncio.CancelledError):
                await get_task
            if not task.done():
                yield (
                    RecognizeStreamEvent(type="heartbeat", stage="recognizing").model_dump_json(exclude_none=True)
                    + "\n"
                )

        # task 完成前最后一次 on_partial 和 task 本身的 return 可能落在同一个
        # event loop tick 里，上面的 asyncio.wait 不保证一定先取到它——收尾时
        # 把队列剩余的快照排空，避免最后一批词丢事件（不会重复：每条只会被
        # 循环里的 get_task 或者这里的 drain 之一消费一次）。
        while not partial_queue.empty():
            yield (
                RecognizeStreamEvent(
                    type="partial",
                    data=_build_recognize_response(partial_queue.get_nowait(), existing_words),
                ).model_dump_json(exclude_none=True)
                + "\n"
            )

        response = _build_recognize_response(task.result(), existing_words)
        yield RecognizeStreamEvent(type="result", data=response).model_dump_json(exclude_none=True) + "\n"
    except RecognitionFailedError:
        yield (
            RecognizeStreamEvent(type="error", message="识别失败，请重新拍摄").model_dump_json(exclude_none=True)
            + "\n"
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("vocabulary_recognize_stream_failed")
        yield (
            RecognizeStreamEvent(type="error", message="识别失败，请稍后重试").model_dump_json(exclude_none=True)
            + "\n"
        )
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@router.post("/recognize", response_model=RecognizeResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_recognize"][0])
async def recognize(
    request: Request,
    image: UploadFile = File(...),
    ocr_words: list[str] = Form(default=[]),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """上传图片，识别出候选英语单词（不落库、不存图）。

    ocr_words 是 iOS 端 Apple Vision 本地 OCR 抠出的候选词，作为参考线索传给视觉
    LLM，与模型自己看图的识别结果综合取并集，提高召回；为空则退化为纯看图识别。
    """
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="图片为空")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        # 不再 raise 413：iOS 客户端拍照后会压缩到 850KB 再上传，正常用户流程
        # 永远碰不到这个上限——这里只是给绕过 iOS 客户端、用 curl/Postman 直发
        # 大图的调用方留一个清晰的日志入口，方便排查；继续走识别流程，万一
        # 上游能处理也能拿到结果（边缘代理对 ~1MB 的实际硬限制比这个稍微大
        # 一些，500KB 以上的差距可能才会真正卡掉）。
        logger.warning(
            "vocabulary_image_oversize",
            bytes=len(image_bytes),
            limit=_MAX_IMAGE_BYTES,
        )

    try:
        recognized = await recognize_words_from_image(
            image_bytes, image.content_type or "image/jpeg", ocr_hint=ocr_words
        )
    except RecognitionFailedError as exc:
        raise HTTPException(status_code=502, detail="识别失败，请重新拍摄") from exc

    existing = await word_service.get_existing_words(db, user.id)
    return _build_recognize_response(recognized, existing)


@router.post("/recognize/stream", response_class=StreamingResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_recognize"][0])
async def recognize_stream(
    request: Request,
    image: UploadFile = File(...),
    ocr_words: list[str] = Form(default=[]),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """上传图片并用 NDJSON 心跳保持长时间识别连接活跃。"""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="图片为空")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        # 跟 /recognize 一致：不再抛 413，只记 warning。理由见上面那一段注释。
        logger.warning(
            "vocabulary_image_oversize",
            bytes=len(image_bytes),
            limit=_MAX_IMAGE_BYTES,
            stream=True,
        )

    existing = await word_service.get_existing_words(db, user.id)
    events = _stream_recognition_events(
        lambda on_partial: recognize_words_from_image(
            image_bytes,
            image.content_type or "image/jpeg",
            ocr_hint=ocr_words,
            on_partial=on_partial,
        ),
        existing_words=existing,
    )
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tts")
@limiter.limit("60/minute")
async def tts(
    request: Request,
    word: str = Query(..., min_length=1, max_length=1000),
    accent: Literal["us", "uk"] = Query(default="us"),
    user: VocabularyUser = Depends(get_current_vocab_user),
):
    """使用 MiniMax Speech HD 返回单词或完整英文例句的高质量 MP3。

    仅登录用户可用，供应商密钥不会下发客户端。未配置时返回 503；客户端播放
    单词时可继续回退到有道，例句则跳过本次播放。
    """
    try:
        audio = await synthesize_speech(word, accent)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="高清发音暂不可用") from exc
    except TTSSynthesisError as exc:
        raise HTTPException(status_code=502, detail="发音生成失败，请稍后再试") from exc

    # 相同文本、口音和服务端音色的结果稳定，允许客户端/边缘缓存一周以减少调用。
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.post("/words/batch", response_model=WordsBatchCreateResponse)
async def add_words_batch(
    payload: WordsBatchCreateRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """批量加入生词库，自动按大小写不敏感去重。"""
    try:
        created_rows, skipped = await word_service.add_words_with_dedup(
            db, user.id, [w.model_dump() for w in payload.words]
        )
    except IntegrityError as exc:
        # 并发请求提交完全相同的词时，应用层去重之间会有竞态窗口，唯一约束兜底拦截，
        # 转成友好提示而不是让请求 500——重新拉取生词库即可看到最新状态。
        await db.rollback()
        raise HTTPException(status_code=409, detail="部分单词提交冲突，请刷新生词库后重试") from exc
    return WordsBatchCreateResponse(
        created=[VocabularyWordResponse.model_validate(r) for r in created_rows],
        skipped_existing=skipped,
    )


@router.get("/words", response_model=VocabularyWordListResponse)
async def list_words_endpoint(
    status: Literal["new", "fuzzy", "known"] | None = Query(default=None),
    q: str | None = Query(default=None),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """生词库列表，支持按状态筛选和关键词搜索。"""
    rows = await word_service.list_words(db, user.id, status=status, query=q)
    return VocabularyWordListResponse(words=[VocabularyWordResponse.model_validate(r) for r in rows])


@router.get("/words/{word_id}", response_model=VocabularyWordResponse)
async def get_word_detail(
    word_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """单词详情。"""
    word = await word_service.get_word(db, user.id, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    return VocabularyWordResponse.model_validate(word)


@router.delete("/words/{word_id}")
async def delete_word_endpoint(
    word_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """删除单词。"""
    ok = await word_service.delete_word(db, user.id, word_id)
    if not ok:
        raise HTTPException(status_code=404, detail="单词不存在")
    return {"deleted": True}


@router.get("/stats", response_model=VocabularyStatsResponse)
async def vocabulary_stats(
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """生词库计数汇总：待复习数 + 三个状态各多少 + 总数。

    iOS 的播放列表面板要在每个分组旁显示词数，靠这个接口一次拿全，不用把整个
    生词库拉下来自己数。
    """
    stats = await word_service.get_stats(db, user.id)
    return VocabularyStatsResponse(
        due_count=stats["due_count"],
        new_count=stats["new_count"],
        fuzzy_count=stats["fuzzy_count"],
        known_count=stats["known_count"],
        total_count=stats["total_count"],
    )


@router.get("/review/queue", response_model=ReviewQueueResponse)
async def review_queue(
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """待复习队列。"""
    rows = await word_service.get_review_queue(db, user.id)
    return ReviewQueueResponse(words=[VocabularyWordResponse.model_validate(r) for r in rows])


@router.post("/words/{word_id}/review", response_model=ReviewSubmitResponse)
async def submit_review_endpoint(
    word_id: uuid.UUID,
    payload: ReviewSubmitRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """提交一次复习结果，更新 SM-2 状态。"""
    word = await word_service.submit_review(db, user.id, word_id, payload.rating)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    logger.info("vocabulary_review_submitted", word_id=str(word_id), rating=payload.rating)
    return ReviewSubmitResponse(word=VocabularyWordResponse.model_validate(word))
