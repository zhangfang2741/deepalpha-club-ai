"""验证可以把平台 llm_registry 的实例注入 TradingAgentsGraph。

TradingAgents 默认用自己的 build_chat_model() 造 LLM，会绕开平台的注册表、
密钥管理、token 上限与温度设置。我们改为预置 __dict__ 抢占它的
cached_property。这个机制依赖它的内部实现，本测试是回归防线：
升级 tradingagents 版本后若此测试失败，说明注入已失效，绝不能忽略。
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from tradingagents import TradingAgentsConfig, TradingAgentsGraph


def _config(tmp_path: Path) -> TradingAgentsConfig:
    """构造一份最小可用配置。这几个字段在 TradingAgentsConfig 中是必填的。"""
    return TradingAgentsConfig(
        results_dir=tmp_path,  # data_cache_dir 是它的只读 property，派生自 results_dir
        llm_provider="openai",  # 注入生效后此字段不再被消费，仅作日志元数据
        deep_think_llm="platform-deep",
        quick_think_llm="platform-quick",
        response_language="zh-CN",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,  # 字段带 ge=30 约束，不可更小
    )


def test_injected_llms_preempt_internal_construction(tmp_path: Path) -> None:
    """预置 __dict__ 后，读取到的是我们注入的实例，且 _create_llm 从未被调用。"""
    graph = TradingAgentsGraph(config=_config(tmp_path))

    calls: list[str] = []
    graph._create_llm = lambda model: calls.append(model)  # type: ignore[method-assign]

    deep = GenericFakeChatModel(messages=iter(["deep"]))
    quick = GenericFakeChatModel(messages=iter(["quick"]))
    # pydantic 把 __dict__ 标注成 MappingProxyType，运行时其实是可写的普通 dict
    graph.__dict__["deep_thinking_llm"] = deep  # type: ignore[index]
    graph.__dict__["quick_thinking_llm"] = quick  # type: ignore[index]

    assert graph.deep_thinking_llm is deep
    assert graph.quick_thinking_llm is quick
    assert calls == [], "注入失效：TradingAgents 自建了 LLM，会绕开平台密钥与配置"


def test_without_injection_internal_construction_is_used(tmp_path: Path) -> None:
    """反向对照：不注入时它会走自己的 _create_llm。

    这条断言保证上一个测试不是因为 _create_llm 本来就不被调用而假通过。
    """
    graph = TradingAgentsGraph(config=_config(tmp_path))

    calls: list[str] = []

    def _fake_create(model: str) -> GenericFakeChatModel:
        calls.append(model)
        return GenericFakeChatModel(messages=iter(["x"]))

    graph._create_llm = _fake_create  # type: ignore[method-assign]

    _ = graph.deep_thinking_llm
    _ = graph.quick_thinking_llm

    assert calls == ["platform-deep", "platform-quick"]
