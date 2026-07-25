# app/api/v1/vocabulary/words.py
"""WordLens 拍照识别 + 生词库 + 复习 API。

不用 `from __future__ import annotations`：`recognize` 挂了 slowapi 的
@limiter.limit() 装饰器，它会让 FastAPI 把 body/表单参数的类型注解解析成未展开
的 ForwardRef，导致参数被误判成 query 参数（详见 app/api/v1/vocabulary/auth.py
顶部同样的说明）。
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
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
    ReviewQueueResponse,
    ReviewSubmitRequest,
    ReviewSubmitResponse,
    VocabularyWordListResponse,
    VocabularyWordResponse,
    WordsBatchCreateRequest,
    WordsBatchCreateResponse,
)
from app.services.vocabulary import words as word_service
from app.services.vocabulary.recognizer import RecognitionFailedError, recognize_words_from_image

from .dependencies import get_current_vocab_user

router = APIRouter()

# 实测 Railway 边缘代理对请求体有约 1MB 的硬限制：超过会在到达这里之前就被
# 拒绝，返回一个我们的错误处理捕获不到的裸 500（700KB 能过，900KB 必 500）。
# 这个校验对走边缘代理的正常请求基本不会触发（客户端应该在上传前就把图片
# 压缩到安全体积），留着是给绕过边缘直连本服务的调用方一个干净的错误提示。
_MAX_IMAGE_BYTES = 800 * 1024  # 800KB，对齐边缘代理的实际限制


@router.post("/recognize", response_model=RecognizeResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["vocabulary_recognize"][0])
async def recognize(
    request: Request,
    image: UploadFile = File(...),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """上传图片，识别出候选英语单词（不落库、不存图）。"""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="图片为空")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片过大，请控制在 10MB 以内")

    try:
        recognized = await recognize_words_from_image(image_bytes, image.content_type or "image/jpeg")
    except RecognitionFailedError as exc:
        raise HTTPException(status_code=502, detail="识别失败，请重新拍摄") from exc

    existing = await word_service.get_existing_words(db, user.id)
    new_words = word_service.filter_new_words(existing, [w.word for w in recognized])
    new_words_lower = {w.lower() for w in new_words}

    candidates = [
        RecognizedWordSchema(
            word=w.word,
            phonetic_ipa=w.phonetic_ipa,
            part_of_speech=w.part_of_speech,
            definition_zh=w.definition_zh,
            already_in_library=w.word.lower() not in new_words_lower,
        )
        for w in recognized
    ]
    return RecognizeResponse(candidates=candidates)


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
