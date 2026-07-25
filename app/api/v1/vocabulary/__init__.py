# app/api/v1/vocabulary/__init__.py
"""WordLens 拍照背单词模块路由汇总。"""
from fastapi import APIRouter

from .auth import router as auth_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["vocabulary-auth"])
