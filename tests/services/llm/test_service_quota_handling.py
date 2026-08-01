"""llm_service 在配额耗尽 / 瞬时限流下的行为契约。

历史 bug：`llm_service` 只 except openai 的异常类型，`LLM_PROVIDER=claude` 时
anthropic 异常直接穿透——不重试、不换模型、也识别不出配额问题。这组测试锁死
修复后的两条行为：

1. 额度用尽 → 立刻抛 `LLMQuotaExhausted`，**不重试也不换模型**（重试救不了，
   只会让用户多等几十秒才看到一句语焉不详的失败）。
2. 瞬时限流 → 换下一个模型继续试，全部失败才抛 `RuntimeError`。
"""

import anthropic
import httpx
import pytest

from app.services.llm import service as llm_service_module
from app.services.llm.service import LLMQuotaExhausted, llm_service


def _anthropic_429(message: str) -> anthropic.RateLimitError:
    """构造一个 anthropic 侧的 429，模拟 MiniMax 兼容接口的真实返回。"""
    request = httpx.Request("POST", "https://api.minimaxi.com/anthropic/v1/messages")
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": message}}
    response = httpx.Response(429, request=request, json=body)
    return anthropic.RateLimitError(f"Error code: 429 - {body}", response=response, body=body)


_QUOTA_MESSAGE = "已达到 Token Plan 用量上限：请升级 Token Plan 套餐或购买积分补充用量。 (2056)"
_TRANSIENT_MESSAGE = "Number of concurrent requests has exceeded the limit"


class _FailingRunnable:
    """总是抛指定异常的假 LLM，并记录被调用次数。"""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def ainvoke(self, _messages):  # noqa: ANN001, ANN202
        self.calls += 1
        raise self.error


@pytest.fixture
def patched_registry(monkeypatch):
    """把注册表替换成两个假模型，返回工厂以便断言调用次数。"""

    def _install(error: Exception) -> _FailingRunnable:
        runnable = _FailingRunnable(error)
        fake_models = [{"name": "fake-a", "llm": runnable}, {"name": "fake-b", "llm": runnable}]
        monkeypatch.setattr(llm_service_module.llm_registry, "LLMS", fake_models)
        monkeypatch.setattr(
            llm_service_module.llm_registry, "get_all_names", lambda: ["fake-a", "fake-b"]
        )
        monkeypatch.setattr(llm_service_module.llm_registry, "get", lambda name, **kw: runnable)
        return runnable

    return _install


async def test_quota_exhaustion_raises_typed_error(patched_registry) -> None:
    """额度用尽必须抛 LLMQuotaExhausted，而不是把原始 429 直接漏给调用方。"""
    patched_registry(_anthropic_429(_QUOTA_MESSAGE))

    with pytest.raises(LLMQuotaExhausted):
        await llm_service.call([{"role": "user", "content": "hi"}], model_name="fake-a")


async def test_quota_exhaustion_does_not_retry_or_switch_models(patched_registry) -> None:
    """额度用尽时重试和换模型都救不了，必须一次就失败。"""
    runnable = patched_registry(_anthropic_429(_QUOTA_MESSAGE))

    with pytest.raises(LLMQuotaExhausted):
        await llm_service.call([{"role": "user", "content": "hi"}], model_name="fake-a")

    assert runnable.calls == 1


async def test_transient_rate_limit_tries_every_model(patched_registry) -> None:
    """瞬时限流应该走完重试与模型 fallback，最后才报 RuntimeError。"""
    runnable = patched_registry(_anthropic_429(_TRANSIENT_MESSAGE))

    with pytest.raises(RuntimeError) as excinfo:
        await llm_service.call([{"role": "user", "content": "hi"}], model_name="fake-a")

    assert not isinstance(excinfo.value, LLMQuotaExhausted)
    # 两个模型都被试过（每个模型内部还会被 tenacity 重试若干次）。
    assert runnable.calls > 2
