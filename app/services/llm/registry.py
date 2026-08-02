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
    """构建 Anthropic Claude 模型列表。

    当 ANTHROPIC_BASE_URL 指向 MiniMax 兼容接口时，自动切换为 MiniMax 模型列表。
    否则使用官方 Claude 模型。
    """
    from langchain_anthropic import ChatAnthropic

    api_key = SecretStr(settings.ANTHROPIC_API_KEY)
    extra: dict[str, Any] = {}
    if settings.ANTHROPIC_BASE_URL:
        extra["base_url"] = settings.ANTHROPIC_BASE_URL

    # MiniMax Anthropic 兼容接口：base_url 含 "minimax" 时注册 MINIMAX_CLAUDE_MODELS
    # 列表中的模型（名称取模型 ID 小写），可通过 SUPPLY_CHAIN_DISCOVER_MODEL 等按名切换。
    if "minimax" in settings.ANTHROPIC_BASE_URL.lower():
        return [
            {
                "name": model_id.lower(),
                "llm": ChatAnthropic(
                    model=model_id,
                    api_key=api_key,
                    max_tokens=settings.MAX_TOKENS,
                    temperature=settings.DEFAULT_LLM_TEMPERATURE,
                    **extra,
                ),
            }
            for model_id in settings.MINIMAX_CLAUDE_MODELS
        ]

    # 官方 Anthropic Claude 模型
    return [
        {
            "name": "claude-haiku-4-5",
            "llm": ChatAnthropic(
                model="claude-haiku-4-5-20251001",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                **extra,
            ),
        },
        {
            "name": "claude-sonnet-4-5",
            "llm": ChatAnthropic(
                model="claude-sonnet-4-5",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                **extra,
            ),
        },
        {
            "name": "claude-sonnet-4-6",
            "llm": ChatAnthropic(
                model="claude-sonnet-4-6",
                api_key=api_key,
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.DEFAULT_LLM_TEMPERATURE,
                **extra,
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


def build_vision_llm() -> dict[str, Any] | None:
    """构建拍照识别（vocabulary/recognizer）专用的视觉模型，独立于全局 LLM_PROVIDER。

    识别是一次性看图任务，需要一个又快又准的视觉模型，与聊天/其它模块的默认
    provider 解耦。由 ``VOCAB_VISION_PROVIDER`` / ``VOCAB_VISION_MODEL`` 配置，
    换模型只改环境变量、不动代码。token 预算在构造时按各供应商正确的参数名烘焙
    进模型（Gemini 用 ``max_output_tokens``、OpenAI 用 ``max_completion_tokens``、
    Anthropic 用 ``max_tokens``），调用方无需再传 max_tokens。

    Returns:
        ``{"name": model_id, "llm": BaseChatModel}`` 条目；对应供应商的 API key
        未配置时返回 ``None``（调用方据此决定是否追加进注册表）。
    """
    provider = settings.VOCAB_VISION_PROVIDER.lower()
    model_id = settings.VOCAB_VISION_MODEL
    max_tokens = settings.VOCAB_VISION_MAX_TOKENS
    temperature = settings.DEFAULT_LLM_TEMPERATURE

    if provider == "gemini":
        if not settings.GOOGLE_API_KEY:
            logger.warning("vision_llm_skipped_missing_key", provider=provider, model=model_id)
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI

        return {
            "name": model_id,
            "llm": ChatGoogleGenerativeAI(
                model=model_id,
                google_api_key=settings.GOOGLE_API_KEY,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        }

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            logger.warning("vision_llm_skipped_missing_key", provider=provider, model=model_id)
            return None
        from langchain_openai import ChatOpenAI

        return {
            "name": model_id,
            "llm": ChatOpenAI(
                model=model_id,
                api_key=SecretStr(settings.OPENAI_API_KEY),
                model_kwargs={"max_completion_tokens": max_tokens},
                temperature=temperature,
            ),
        }

    if provider in ("claude", "anthropic"):
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("vision_llm_skipped_missing_key", provider=provider, model=model_id)
            return None
        from langchain_anthropic import ChatAnthropic

        extra: dict[str, Any] = {}
        if settings.ANTHROPIC_BASE_URL:
            extra["base_url"] = settings.ANTHROPIC_BASE_URL
        return {
            "name": model_id,
            "llm": ChatAnthropic(
                model=model_id,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                max_tokens=max_tokens,
                temperature=temperature,
                **extra,
            ),
        }

    logger.warning("vision_llm_unknown_provider", provider=provider, model=model_id)
    return None


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

        # 追加拍照识别专用的视觉模型（独立于 LLM_PROVIDER）。同名已存在则不重复追加
        # ——例如全局 provider 恰好就是该视觉模型所属供应商时，builder 里可能已注册。
        vision_entry = build_vision_llm()
        if vision_entry and not any(e["name"] == vision_entry["name"] for e in self.LLMS):
            self.LLMS.append(vision_entry)
            logger.info(
                "vision_llm_registered",
                provider=settings.VOCAB_VISION_PROVIDER,
                model=vision_entry["name"],
            )

        logger.info(
            "llm_registry_initialized",
            provider=provider,
            models=[e["name"] for e in self.LLMS],
        )

    def get(self, model_name: str, **kwargs: Any) -> BaseChatModel:
        """按名称获取 LLM 实例。

        Args:
            model_name: 模型名称（需与 LLMS 列表中的 name 一致）
            **kwargs: 覆盖注册时的构造参数（如 temperature、max_tokens），
                用 ``model_copy(update=...)`` 生成一个新实例，不影响注册表里
                的共享单例。仅用于 ``llm_service.call()`` 的一次性调用路径。

        Returns:
            对应的 BaseChatModel 实例

        Raises:
            ValueError: 模型名称不存在时
        """
        entry = next((e for e in self.LLMS if e["name"] == model_name), None)
        if not entry:
            available = ", ".join(e["name"] for e in self.LLMS)
            raise ValueError(f"模型 '{model_name}' 不存在。可用模型：{available}")
        if not kwargs:
            return entry["llm"]
        return entry["llm"].model_copy(update=kwargs)

    def get_or_default(self, model_name: str | None) -> tuple[BaseChatModel, str]:
        """按名称获取 LLM，找不到（或名称为空）时回退到默认/第一个模型。

        与 ``get()`` 不同，本方法不会抛错，适用于「模型名来自可变配置、不应
        因配置漂移而中断请求」的场景（如供应链实时预览）。

        Args:
            model_name: 期望的模型名称，可为 None 或空串。

        Returns:
            (BaseChatModel 实例, 实际生效的模型名称) 二元组。
        """
        if model_name:
            entry = next((e for e in self.LLMS if e["name"] == model_name), None)
            if entry:
                return entry["llm"], entry["name"]
            logger.warning(
                "requested_model_not_found_using_default",
                requested=model_name,
                available=[e["name"] for e in self.LLMS],
            )
        fallback = settings.DEFAULT_LLM_MODEL
        entry = next((e for e in self.LLMS if e["name"] == fallback), None) or self.LLMS[0]
        return entry["llm"], entry["name"]

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
