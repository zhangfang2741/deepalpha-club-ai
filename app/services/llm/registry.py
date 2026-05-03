# app/services/llm/registry.py
"""LLM 模型注册表：按 LLM_PROVIDER 动态构建，支持 openai / claude / minimax / gemini。"""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


def _build_openai_llms() -> list[dict[str, Any]]:
    """构建 OpenAI 模型列表。"""
    from langchain_openai import ChatOpenAI

    api_key = SecretStr(settings.OPENAI_API_KEY)
    token_limit: dict[str, Any] = {"max_completion_tokens": settings.MAX_TOKENS}
    return [
        {
            "name": "gpt-4o-mini",
            "llm": ChatOpenAI(
                model="gpt-4o-mini",
                api_key=api_key,
                model_kwargs=token_limit,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "gpt-4o",
            "llm": ChatOpenAI(
                model="gpt-4o",
                api_key=api_key,
                model_kwargs=token_limit,
                top_p=0.95 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.8,
                presence_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
                frequency_penalty=0.1 if settings.ENVIRONMENT == Environment.PRODUCTION else 0.0,
            ),
        },
    ]


def _build_claude_llms() -> list[dict[str, Any]]:
    """构建 Anthropic Claude 模型列表。"""
    from langchain_anthropic import ChatAnthropic

    api_key = SecretStr(settings.ANTHROPIC_API_KEY)
    return [
        {
            "name": "claude-haiku-4-5",
            "llm": ChatAnthropic(
                model="claude-haiku-4-5-20251001",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "claude-sonnet-4-5",
            "llm": ChatAnthropic(
                model="claude-sonnet-4-5",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "claude-sonnet-4-6",
            "llm": ChatAnthropic(
                model="claude-sonnet-4-6",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
    ]


def _build_minimax_llms() -> list[dict[str, Any]]:
    """构建 MiniMax 模型列表（OpenAI 兼容接口）。"""
    from langchain_openai import ChatOpenAI

    api_key = SecretStr(settings.MINIMAX_API_KEY)
    return [
        {
            "name": "minimax-text-01",
            "llm": ChatOpenAI(
                model="MiniMax-Text-01",
                api_key=api_key,
                base_url=settings.MINIMAX_BASE_URL,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "minimax-m1",
            "llm": ChatOpenAI(
                model="MiniMax-M1",
                api_key=api_key,
                base_url=settings.MINIMAX_BASE_URL,
                max_tokens=settings.MAX_TOKENS,
            ),
        },
    ]


def _build_gemini_llms() -> list[dict[str, Any]]:
    """构建 Google Gemini 模型列表。"""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return [
        {
            "name": "gemini-2.0-flash",
            "llm": ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=settings.GOOGLE_API_KEY,
                max_output_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
            ),
        },
        {
            "name": "gemini-2.5-pro",
            "llm": ChatGoogleGenerativeAI(
                model="gemini-2.5-pro-preview-05-06",
                google_api_key=settings.GOOGLE_API_KEY,
                max_output_tokens=settings.MAX_TOKENS,
            ),
        },
    ]


_BUILDERS = {
    "openai": _build_openai_llms,
    "claude": _build_claude_llms,
    "minimax": _build_minimax_llms,
    "gemini": _build_gemini_llms,
}


class LLMRegistry:
    """按 LLM_PROVIDER 动态构建模型注册表。

    通过环境变量 LLM_PROVIDER 切换供应商：
        LLM_PROVIDER=claude  → 使用 Claude 系列
        LLM_PROVIDER=openai  → 使用 GPT 系列
        LLM_PROVIDER=minimax → 使用 MiniMax 系列
        LLM_PROVIDER=gemini  → 使用 Gemini 系列
    """

    def __init__(self) -> None:
        provider = settings.LLM_PROVIDER.lower()
        builder = _BUILDERS.get(provider)
        if builder is None:
            raise ValueError(
                f"不支持的 LLM_PROVIDER: '{provider}'。可选值：{list(_BUILDERS.keys())}"
            )
        self.LLMS: list[dict[str, Any]] = builder()
        logger.info(
            "llm_registry_initialized",
            provider=provider,
            models=[e["name"] for e in self.LLMS],
        )

    def get(self, model_name: str, **kwargs: Any) -> BaseChatModel:
        """按名称获取 LLM 实例。

        Args:
            model_name: 模型名称（需与 LLMS 列表中的 name 一致）
            **kwargs: 保留参数（当前未使用）

        Returns:
            对应的 BaseChatModel 实例

        Raises:
            ValueError: 模型名称不存在时
        """
        entry = next((e for e in self.LLMS if e["name"] == model_name), None)
        if not entry:
            available = ", ".join(e["name"] for e in self.LLMS)
            raise ValueError(f"模型 '{model_name}' 不存在。可用模型：{available}")
        if kwargs:
            logger.debug("llm_get_with_kwargs_ignored", model=model_name, kwargs=list(kwargs.keys()))
        return entry["llm"]

    def get_all_names(self) -> list[str]:
        """返回所有已注册模型名称。"""
        return [e["name"] for e in self.LLMS]

    def get_model_at_index(self, index: int) -> dict[str, Any]:
        """按索引获取模型条目，索引越界时返回第一个。"""
        if 0 <= index < len(self.LLMS):
            return self.LLMS[index]
        return self.LLMS[0]

    def get_default(self) -> BaseChatModel:
        """返回 DEFAULT_LLM_MODEL 指定的模型，找不到时回退到列表第一个。"""
        name = settings.DEFAULT_LLM_MODEL
        try:
            return self.get(name)
        except ValueError:
            logger.warning("default_model_not_found_using_first", requested=name)
            return self.LLMS[0]["llm"]


# 全局单例（由 service.py 使用）
llm_registry = LLMRegistry()
