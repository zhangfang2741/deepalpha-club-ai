"""LLM service with retries, circular fallback, and optional structured output."""

import asyncio
import logging
from typing import (
    Any,
    Callable,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from openai import OpenAIError
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import logger
from app.services.llm.errors import is_provider_error, is_quota_exhausted, is_retryable
from app.services.llm.registry import llm_registry

T = TypeVar("T", bound=BaseModel)


class LLMQuotaExhausted(OpenAIError):
    """A provider's long-window quota is exhausted.

    保持继承 ``OpenAIError`` 以兼容既有调用方（``app/tasks/supply_chain.py``），
    但判定本身已经与供应商 SDK 解耦——见 ``app.services.llm.errors``。
    """

    def __init__(self, provider: str, retry_after_hint: int | None = None) -> None:
        """Record provider identity and an optional retry window."""
        self.provider = provider
        self.retry_after_hint = retry_after_hint
        super().__init__(f"{provider} quota exhausted")


class LLMService:
    """Service for managing LLM calls with retries and circular fallback.

    Two distinct execution paths:

    - **Default path** (no model_name / response_format / model_kwargs): uses
      ``self._llm`` which is the tool-bound agent model. Circular fallback
      updates ``self._llm`` so tool bindings are preserved across retries.

    - **One-off path** (any override provided): resolves a fresh, local
      ``Runnable`` for the call without ever touching ``self._llm``, so
      concurrent default-path calls are never affected.
    """

    def __init__(self):
        """Initialize the LLM service with the configured default model."""
        self._llm: Any = None  # BaseChatModel pre-bind_tools, Runnable after
        self._current_model_index: int = 0
        self._bound_tools: List = []

        all_names = llm_registry.get_all_names()
        try:
            self._current_model_index = all_names.index(settings.DEFAULT_LLM_MODEL)
            self._llm = llm_registry.get(settings.DEFAULT_LLM_MODEL)
            logger.info(
                "llm_service_initialized",
                default_model=settings.DEFAULT_LLM_MODEL,
                model_index=self._current_model_index,
                total_models=len(all_names),
                environment=settings.ENVIRONMENT.value,
            )
        except Exception as e:
            self._current_model_index = 0
            self._llm = llm_registry.LLMS[0]["llm"]
            logger.warning(
                "default_model_not_found_using_first",
                requested=settings.DEFAULT_LLM_MODEL,
                using=all_names[0] if all_names else "none",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @overload
    async def call(
        self,
        messages: LanguageModelInput,
        model_name: Optional[str] = ...,
        response_format: None = ...,
        timeout: Optional[float] = ...,
        **model_kwargs: Any,
    ) -> BaseMessage: ...

    @overload
    async def call(
        self,
        messages: LanguageModelInput,
        model_name: Optional[str] = ...,
        *,
        response_format: Type[T],
        timeout: Optional[float] = ...,
        **model_kwargs: Any,
    ) -> T: ...

    async def call(
        self,
        messages: LanguageModelInput,
        model_name: Optional[str] = None,
        response_format: Optional[Type[BaseModel]] = None,
        timeout: Optional[float] = None,
        **model_kwargs: Any,
    ) -> Union[BaseMessage, BaseModel]:
        """Call the LLM with retries and circular fallback.

        Args:
            messages: Conversation messages to send.
            model_name: Override the model. ``None`` uses the current default.
            response_format: Pydantic schema for structured output. When
                provided the call chains ``.with_structured_output(schema)``
                and returns a validated instance of that schema instead of a
                raw ``BaseMessage``.
            timeout: Total timeout budget in seconds for this call. ``None``
                uses ``settings.LLM_TOTAL_TIMEOUT``. Heavy one-off calls (e.g.
                summarizing a long transcript) can request a larger budget.
            **model_kwargs: Extra kwargs forwarded to ``LLMRegistry.get`` when
                constructing a one-off model instance (e.g. ``temperature``,
                ``max_tokens``, ``reasoning``).

        Returns:
            ``BaseMessage`` when ``response_format`` is ``None``, otherwise a
            validated instance of ``response_format``.

        Raises:
            RuntimeError: When all models fail after retries or the total
                timeout budget is exceeded.
        """
        total_timeout = timeout if timeout is not None else settings.LLM_TOTAL_TIMEOUT
        try:
            return await asyncio.wait_for(
                self._call_with_fallback(messages, model_name, response_format, model_kwargs),
                timeout=total_timeout,
            )
        except asyncio.TimeoutError:
            logger.exception(
                "llm_total_timeout_exceeded",
                timeout_seconds=total_timeout,
            )
            raise RuntimeError(f"llm call timed out after {total_timeout}s total budget")

    def get_llm(self) -> Any:
        """Return the current tool-bound default LLM instance.

        Returns:
            Current ``BaseChatModel`` instance or ``None`` if not initialised.
        """
        return self._llm

    def bind_tools(self, tools: List) -> "LLMService":
        """Bind tools to the default LLM instance.

        Args:
            tools: List of tools to bind.

        Returns:
            Self for method chaining.
        """
        if self._llm:
            self._bound_tools = tools
            self._llm = self._llm.bind_tools(tools)
            logger.debug("tools_bound_to_llm", tool_count=len(tools))
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(settings.MAX_LLM_CALL_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # 按「行为」而不是「异常类型」决定是否重试。用 retry_if_exception_type 挂
        # 具体 SDK 的类，换供应商后会静默失效——实测 LLM_PROVIDER=claude 时
        # anthropic 的异常一个都匹配不上，重试与 fallback 全成了死代码。
        retry=retry_if_exception(is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _invoke_with_retry(self, llm: Any, messages: LanguageModelInput) -> Any:
        """Invoke an LLM runnable with automatic per-model retry logic.

        Args:
            llm: Any LangChain ``Runnable`` (plain model or structured-output chain).
            messages: Messages to send.

        Returns:
            The runnable's response (``BaseMessage`` or a ``BaseModel`` instance).

        Raises:
            LLMQuotaExhausted: 账号额度用尽——重试与换模型都救不了，立刻抛出。
            Exception: 其余供应商错误在重试耗尽后原样向上传。
        """
        try:
            response = await llm.ainvoke(messages)
            logger.debug("llm_call_successful")
            return response
        except Exception as e:
            if is_quota_exhausted(e):
                # 额度用尽是终态：继续重试只会让调用方多等几十秒，再收到一句
                # 语焉不详的失败。转成带类型的异常，让上层能如实告诉用户。
                logger.error(
                    "llm_quota_exhausted",
                    provider=settings.LLM_PROVIDER,
                    error=str(e),
                )
                raise LLMQuotaExhausted(
                    settings.LLM_PROVIDER, settings.SUPPLY_CHAIN_QUOTA_WINDOW_SECONDS
                ) from e
            if is_retryable(e):
                logger.warning(
                    "llm_call_failed_retrying",
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
            else:
                logger.error(
                    "llm_call_failed",
                    error_type=type(e).__name__,
                    error=str(e),
                )
            raise

    def _switch_to_next_model(self) -> bool:
        """Advance the default model to the next entry in the registry (circular).

        Mutates ``self._llm`` and ``self._current_model_index`` so tool bindings
        survive model switches on the default agent path.

        Returns:
            ``True`` on success, ``False`` if the switch failed.
        """
        try:
            next_index = (self._current_model_index + 1) % len(llm_registry.LLMS)
            next_entry = llm_registry.get_model_at_index(next_index)
            logger.warning(
                "switching_to_next_model",
                from_index=self._current_model_index,
                to_index=next_index,
                to_model=next_entry["name"],
            )
            self._current_model_index = next_index
            self._llm = next_entry["llm"]
            if self._bound_tools:
                self._llm = self._llm.bind_tools(self._bound_tools)
            logger.info("model_switched", new_model=next_entry["name"], new_index=next_index)
            return True
        except Exception as e:
            logger.error("model_switch_failed", error=str(e))
            return False

    async def _call_with_fallback(
        self,
        messages: LanguageModelInput,
        model_name: Optional[str],
        response_format: Optional[Type[BaseModel]],
        model_kwargs: dict,
    ) -> Union[BaseMessage, BaseModel]:
        """Build path-specific strategies and delegate to the shared fallback loop.

        One-off path (any override set):
            ``get_target`` builds a fresh registry instance each attempt.
            ``advance`` increments a local index — ``self._llm`` is never touched.

        Default path (no overrides):
            ``get_target`` returns ``self._llm`` (tool-bound).
            ``advance`` calls ``_switch_to_next_model`` so bindings persist.
        """

        def _override_target(idx: int) -> Any:
            base = llm_registry.get(llm_registry.LLMS[idx]["name"], **model_kwargs)
            return base.with_structured_output(response_format) if response_format else base

        def _default_target(_: int) -> Any:
            return self._llm

        def _default_advance(_: int) -> Optional[int]:
            return self._current_model_index if self._switch_to_next_model() else None

        if model_name or response_format or model_kwargs:
            all_names = llm_registry.get_all_names()
            if model_name and model_name not in all_names:
                logger.error("requested_model_not_found", model_name=model_name)
                raise ValueError(
                    f"model '{model_name}' not found in registry. available models: {', '.join(all_names)}"
                )

            start = all_names.index(model_name) if model_name else self._current_model_index
            total = len(llm_registry.LLMS)
            get_target: Callable[[int], Any] = _override_target

            def _override_advance(idx: int) -> Optional[int]:
                return (idx + 1) % total

            advance: Callable[[int], Optional[int]] = _override_advance
        else:
            start = self._current_model_index
            get_target = _default_target
            advance = _default_advance

        return await self._fallback_loop(messages, start, get_target, advance)

    async def _fallback_loop(
        self,
        messages: LanguageModelInput,
        start: int,
        get_target: Callable[[int], Any],
        advance: Callable[[int], Optional[int]],
    ) -> Any:
        """Shared fallback loop — try each model in turn until one succeeds.

        Args:
            messages: Messages to send.
            start: Registry index to begin from.
            get_target: Returns the ``Runnable`` to invoke for a given index.
            advance: Returns the next index to try, or ``None`` to stop.

        Returns:
            The first successful response.

        Raises:
            RuntimeError: When all models have been exhausted.
        """
        total = len(llm_registry.LLMS)
        current = start
        models_tried = 0
        last_error: Optional[Exception] = None

        for models_tried in range(1, total + 1):
            current_name = llm_registry.LLMS[current]["name"]
            try:
                return await self._invoke_with_retry(get_target(current), messages)
            except LLMQuotaExhausted:
                # 额度是账号级的，注册表里的模型共用同一个 key——换模型同样会被
                # 拒。立刻抛出，别让调用方为一个注定失败的轮换白等一轮。
                logger.error(
                    "llm_quota_exhausted_aborting_fallback",
                    model=current_name,
                    models_tried=models_tried,
                    total_models=total,
                )
                raise
            except Exception as e:
                if not is_provider_error(e):
                    # 我们自己的代码 bug（如模型名拼错）不该被 fallback 吞掉，
                    # 换个模型重试只会把真正的错误藏得更深。
                    raise
                last_error = e
                logger.error(
                    "llm_call_failed_after_retries",
                    model=current_name,
                    models_tried=models_tried,
                    total_models=total,
                    error=str(e),
                )
                if models_tried >= total:
                    logger.error(
                        "all_models_failed", models_tried=models_tried, starting_model=llm_registry.LLMS[start]["name"]
                    )
                    break
                next_idx = advance(current)
                if next_idx is None:
                    logger.error("failed_to_switch_to_next_model")
                    break
                current = next_idx

        raise RuntimeError(
            f"failed to get response from llm after trying {models_tried} models. last error: {str(last_error)}"
        )


llm_service = LLMService()
