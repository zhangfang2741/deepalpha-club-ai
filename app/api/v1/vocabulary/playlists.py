# app/api/v1/vocabulary/playlists.py
"""WordLens 自定义歌单 API。

单独成文件而不是塞进 words.py：后者已经有拍照识别 + 生词 CRUD + 复习三块内容、
355 行，歌单是独立的一块业务，混进去只会让那个文件更难读。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    PlaylistAddWordsRequest,
    PlaylistCreateRequest,
    PlaylistListResponse,
    PlaylistResponse,
    PlaylistUpdateRequest,
    VocabularyWordListResponse,
    VocabularyWordResponse,
)
from app.services.vocabulary import playlists as playlist_service

from .dependencies import get_current_vocab_user

router = APIRouter()


@router.get("/playlists", response_model=PlaylistListResponse)
async def list_playlists_endpoint(
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """歌单列表（含每个歌单的词数）。"""
    rows = await playlist_service.list_playlists(db, user.id)
    return PlaylistListResponse(
        playlists=[
            PlaylistResponse(
                id=playlist.id,
                name=playlist.name,
                word_count=count,
                created_at=playlist.created_at,
            )
            for playlist, count in rows
        ]
    )


@router.post("/playlists", response_model=PlaylistResponse)
async def create_playlist_endpoint(
    payload: PlaylistCreateRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """新建歌单。歌单名在同一用户下唯一，重名返回 409。"""
    try:
        playlist, count = await playlist_service.create_playlist(
            db, user.id, payload.name, payload.word_ids
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="已有同名歌单，换个名字试试") from exc
    logger.info("vocabulary_playlist_created", playlist_id=str(playlist.id), word_count=count)
    return PlaylistResponse(
        id=playlist.id, name=playlist.name, word_count=count, created_at=playlist.created_at
    )


@router.patch("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def update_playlist_endpoint(
    playlist_id: uuid.UUID,
    payload: PlaylistUpdateRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """改名 / 整体替换词表。两个字段都可选，只传其中一个就只改那一项。"""
    try:
        result = await playlist_service.update_playlist(
            db, user.id, playlist_id, name=payload.name, word_ids=payload.word_ids
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="已有同名歌单，换个名字试试") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    playlist, count = result
    return PlaylistResponse(
        id=playlist.id, name=playlist.name, word_count=count, created_at=playlist.created_at
    )


@router.post("/playlists/{playlist_id}/words", response_model=PlaylistResponse)
async def add_words_to_playlist_endpoint(
    playlist_id: uuid.UUID,
    payload: PlaylistAddWordsRequest,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """把一批词并入歌单末尾（生词库多选「加入歌单」用），已在歌单里的自动跳过。"""
    result = await playlist_service.add_words_to_playlist(db, user.id, playlist_id, payload.word_ids)
    if result is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    playlist, count = result
    return PlaylistResponse(
        id=playlist.id, name=playlist.name, word_count=count, created_at=playlist.created_at
    )


@router.delete("/playlists/{playlist_id}")
async def delete_playlist_endpoint(
    playlist_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """删除歌单（只删歌单本身，里面的词仍留在生词库）。"""
    ok = await playlist_service.delete_playlist(db, user.id, playlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return {"deleted": True}


@router.get("/playlists/{playlist_id}/words", response_model=VocabularyWordListResponse)
async def get_playlist_words_endpoint(
    playlist_id: uuid.UUID,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """歌单词表，按用户在编辑页排的顺序返回——就是自动播放的播放顺序。"""
    rows = await playlist_service.get_playlist_words(db, user.id, playlist_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="歌单不存在")
    return VocabularyWordListResponse(words=[VocabularyWordResponse.model_validate(r) for r in rows])
