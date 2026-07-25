# app/api/v1/vocabulary/words.py
"""WordLens 拍照识别 + 生词库 + 复习 API。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.post("/recognize", response_model=RecognizeResponse)
async def recognize(
    image: UploadFile = File(...),
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """上传图片，识别出候选英语单词（不落库、不存图）。"""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="图片为空")

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
    created_rows, skipped = await word_service.add_words_with_dedup(
        db, user.id, [w.model_dump() for w in payload.words]
    )
    return WordsBatchCreateResponse(
        created=[VocabularyWordResponse.model_validate(r) for r in created_rows],
        skipped_existing=skipped,
    )


@router.get("/words", response_model=VocabularyWordListResponse)
async def list_words_endpoint(
    status: str | None = Query(default=None),
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
