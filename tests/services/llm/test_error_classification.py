"""LLM 供应商异常分类测试。

背景：各家 SDK 的异常体系互不继承（`anthropic.RateLimitError` 不是
`openai.RateLimitError` 的子类），历史上 `llm_service` 只 except openai 的类型，
导致 `LLM_PROVIDER=claude` 时重试/fallback/配额检测三套机制全部静默失效。
这组测试锁死「判定必须与供应商无关」这个契约。
"""

import anthropic
import httpx
import openai
import pytest

from app.services.llm.errors import (
    is_provider_error,
    is_quota_exhausted,
    is_retryable,
)


def _anthropic_error(status: int, message: str) -> anthropic.APIStatusError:
    """构造一个带真实 status_code 的 anthropic SDK 异常。"""
    request = httpx.Request("POST", "https://api.minimaxi.com/anthropic/v1/messages")
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": message}}
    response = httpx.Response(status, request=request, json=body)
    error_class = anthropic.RateLimitError if status == 429 else anthropic.APIStatusError
    return error_class(f"Error code: {status} - {body}", response=response, body=body)


def _openai_error(status: int, message: str) -> openai.APIStatusError:
    """构造一个带真实 status_code 的 openai SDK 异常。"""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    body = {"error": {"message": message, "type": "insufficient_quota"}}
    response = httpx.Response(status, request=request, json=body)
    error_class = openai.RateLimitError if status == 429 else openai.APIStatusError
    return error_class(f"Error code: {status} - {body}", response=response, body=body)


# ---------------------------------------------------------------- is_provider_error


def test_recognizes_anthropic_errors_as_provider_errors() -> None:
    """anthropic 异常必须被认成供应商错误——这是历史 bug 的核心。"""
    assert is_provider_error(_anthropic_error(429, "rate limited")) is True


def test_recognizes_openai_errors_as_provider_errors() -> None:
    """openai 路径的行为不能因为这次解耦而退化。"""
    assert is_provider_error(_openai_error(429, "rate limited")) is True


def test_plain_exception_is_not_a_provider_error() -> None:
    """普通异常（如代码 bug）不该被当成供应商故障吞进 fallback 逻辑。"""
    assert is_provider_error(ValueError("model not found")) is False


# ---------------------------------------------------------------- is_quota_exhausted


def test_detects_minimax_chinese_quota_message() -> None:
    """MiniMax 的中文配额文案必须被识别（旧关键词表一个都不命中）。"""
    error = _anthropic_error(
        429, "已达到 Token Plan 用量上限：请升级 Token Plan 套餐或购买积分补充用量。 (2056)"
    )
    assert is_quota_exhausted(error) is True


def test_detects_openai_insufficient_quota() -> None:
    """openai 的 insufficient_quota 仍然要识别。"""
    assert is_quota_exhausted(_openai_error(429, "You exceeded your current quota")) is True


def test_transient_rate_limit_is_not_quota_exhaustion() -> None:
    """并发打满这种临时限流应该重试，不能误判成「额度用完」让用户去充值。"""
    error = _anthropic_error(429, "Number of concurrent requests has exceeded the limit")
    assert is_quota_exhausted(error) is False


def test_payment_required_is_quota_exhaustion() -> None:
    """402 语义上就是欠费，无需匹配文案。"""
    assert is_quota_exhausted(_anthropic_error(402, "payment required")) is True


# ---------------------------------------------------------------- is_retryable


def test_transient_rate_limit_is_retryable() -> None:
    """临时限流值得退避重试。"""
    error = _anthropic_error(429, "Number of concurrent requests has exceeded the limit")
    assert is_retryable(error) is True


def test_quota_exhaustion_is_not_retryable() -> None:
    """额度用尽时重试和换模型都救不了，只会白白让用户多等几十秒。"""
    error = _anthropic_error(429, "已达到 Token Plan 用量上限：请升级 Token Plan 套餐。 (2056)")
    assert is_retryable(error) is False


def test_server_error_is_retryable() -> None:
    """5xx 是典型的瞬时故障。"""
    assert is_retryable(_anthropic_error(503, "upstream unavailable")) is True


def test_auth_error_is_not_retryable() -> None:
    """401 是配置问题，重试多少次都一样。"""
    assert is_retryable(_anthropic_error(401, "invalid api key")) is False


@pytest.mark.parametrize("timeout_error", [openai.APITimeoutError, anthropic.APITimeoutError])
def test_timeouts_are_retryable_for_both_sdks(timeout_error: type) -> None:
    """两家 SDK 的超时异常都要能重试。"""
    request = httpx.Request("POST", "https://example.invalid/v1/messages")
    assert is_retryable(timeout_error(request=request)) is True
