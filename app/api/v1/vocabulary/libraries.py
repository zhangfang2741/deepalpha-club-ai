# app/api/v1/vocabulary/libraries.py
"""WordLens 内置词库 API：列出分组词库 + 整本导入生词库。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.core.logging import logger
from app.db.session import get_db
from app.models.vocabulary import VocabularyUser
from app.schemas.vocabulary import (
    LibraryBookSchema,
    LibraryGroupSchema,
    LibraryImportResponse,
    LibraryListResponse,
)
from app.services.vocabulary import libraries as library_service

from .dependencies import get_current_vocab_user

router = APIRouter()


@router.get("/libraries", response_model=LibraryListResponse)
async def list_libraries(
    user: VocabularyUser = Depends(get_current_vocab_user),
):
    """列出全部内置词库（分组 + 每本元信息，不含词条）。

    数据固定内置、与用户无关，但仍要求登录：设置页在登录态下才可达，且导入
    接口也需登录，列表与导入保持同一鉴权面更简单。
    """
    groups = [
        LibraryGroupSchema(
            key=g["key"],
            title=g["title"],
            books=[LibraryBookSchema(**b) for b in g["books"]],
        )
        for g in library_service.list_groups()
    ]
    return LibraryListResponse(groups=groups)


@router.post("/libraries/{book_id}/import", response_model=LibraryImportResponse)
@limiter.limit("20/minute")
async def import_library(
    request: Request,
    book_id: str,
    user: VocabularyUser = Depends(get_current_vocab_user),
    db: AsyncSession = Depends(get_db),
):
    """把指定内置词库整本并入当前用户生词库，自动跨全库去重。

    幂等：已在生词库中的词会被跳过而不是报错，重复导入同一本只会把之前漏掉的
    补齐。大词库（如专八 12197 词）在服务层分块写入，避开数据库单语句参数上限。
    """
    if library_service.get_book_meta(book_id) is None:
        raise HTTPException(status_code=404, detail="词库不存在")

    try:
        imported, skipped = await library_service.import_book(db, user.id, book_id)
    except IntegrityError as exc:
        # 并发导入同一本时，应用层去重与唯一约束之间存在竞态窗口，兜底转成 409。
        await db.rollback()
        raise HTTPException(status_code=409, detail="导入冲突，请刷新生词库后重试") from exc

    logger.info(
        "vocabulary_library_imported",
        book_id=book_id,
        imported=imported,
        skipped=skipped,
    )
    return LibraryImportResponse(imported=imported, skipped=skipped)
