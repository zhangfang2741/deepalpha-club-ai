# app/api/v1/vocabulary/__init__.py
"""WordLens 拍照背单词模块路由汇总。"""
from fastapi import APIRouter

from .auth import router as auth_router
from .playlists import router as playlists_router
from .words import router as words_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["vocabulary-auth"])
router.include_router(words_router, tags=["vocabulary-words"])
router.include_router(playlists_router, tags=["vocabulary-playlists"])
