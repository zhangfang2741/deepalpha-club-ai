"""LLM 供应商异常的统一判定。

各家 SDK 的异常体系互不继承——`anthropic.RateLimitError` 既不是
`openai.RateLimitError` 也不是 `openai.OpenAIError` 的子类。历史上
`llm_service` 只 `except` openai 的类型，于是 `LLM_PROVIDER=claude` 时重试、
模型 fallback、配额检测三套机制全部变成死代码，异常直接穿透到调用方，配额
信息也在上层的 `except Exception` 里被吞成一句「识别失败」。

所以这里不按异常类型判定，而是按**行为特征**判定：HTTP 状态码 + 错误文案。
新增供应商时不需要回来改这个文件，也不会再出现「换了 SDK 就静默失效」。
"""
from __future__ import annotations

# 供应商 SDK 的顶层包名。异常的 __module__ 落在这些包里，才认为是「调用外部
# 模型服务失败」，而不是我们自己的代码 bug（后者不该被 fallback 逻辑吞掉）。
_PROVIDER_SDK_MODULES = frozenset({"openai", "anthropic", "google", "langchain_google_genai"})

# 重试和换模型救得了的瞬时故障：限流、请求超时、上游 5xx。
_RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})

# 402 Payment Required 语义上就是欠费，不必再匹配文案。
_QUOTA_STATUSES = frozenset({402})

# 「账号额度/套餐用尽」的文案特征。区分这一类的意义在于：它和临时限流同样返回
# 429，但重试与换模型都救不了——只会让用户多等几十秒再看到一句语焉不详的失败。
# 命中后应当立刻失败，并把「额度用完了」如实告诉用户。
_QUOTA_KEYWORDS = (
    # OpenAI / 通用英文
    "quota",
    "insufficient_quota",
    "insufficient balance",
    "insufficient credit",
    "billing",
    "exceeded your current",
    # Anthropic 长窗口配额
    "5 hour",
    "5-hour",
    "5 小时",
    "rate limit window",
    # MiniMax 中文文案，实测原文：
    # 「已达到 Token Plan 用量上限：请升级 Token Plan 套餐或购买积分补充用量。 (2056)」
    "用量上限",
    "额度",
    "余额不足",
    "购买积分",
    "欠费",
    "充值",
)

# MiniMax 的业务错误码，会同时出现在 HTTP body 和消息文本里。
_QUOTA_PROVIDER_CODES = ("2056",)


def _status_code(exc: BaseException) -> int | None:
    """取异常携带的 HTTP 状态码。

    openai / anthropic 的 ``APIStatusError`` 都有 ``status_code``；部分包装类
    只带 ``response``。两个来源都试一遍，取不到就返回 None。
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _root_module(exc: BaseException) -> str:
    """取异常所属的顶层包名，用于识别是否来自供应商 SDK。"""
    return type(exc).__module__.split(".", 1)[0]


def is_provider_error(exc: BaseException) -> bool:
    """是否为 LLM 供应商 SDK 抛出的 API 错误。

    用来替代 ``except OpenAIError``——后者在非 openai 供应商下永远不匹配。
    """
    if _root_module(exc) in _PROVIDER_SDK_MODULES:
        return True
    # LangChain 有时会把底层异常包一层，但仍保留 status_code/response 特征。
    return _status_code(exc) is not None and hasattr(exc, "response")


def is_quota_exhausted(exc: BaseException) -> bool:
    """是否为「账号额度/套餐用尽」。

    重试和换模型都救不了这一类错误，调用方应立刻失败并如实提示用户。
    """
    status = _status_code(exc)
    if status in _QUOTA_STATUSES:
        return True
    if status != 429:
        return False
    message = str(exc).lower()
    if any(code in message for code in _QUOTA_PROVIDER_CODES):
        return True
    return any(keyword in message for keyword in _QUOTA_KEYWORDS)


def is_retryable(exc: BaseException) -> bool:
    """是否值得退避重试（瞬时限流、超时、上游 5xx）。

    额度用尽不算——见 ``is_quota_exhausted``。
    """
    if is_quota_exhausted(exc):
        return False
    # 超时类异常通常不带 status_code，按类名识别；两家 SDK 都叫 APITimeoutError。
    if type(exc).__name__ in {"APITimeoutError", "APIConnectionError"}:
        return True
    return _status_code(exc) in _RETRYABLE_STATUSES
