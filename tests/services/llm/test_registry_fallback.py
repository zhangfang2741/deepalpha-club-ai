"""LLMRegistry 容错解析测试。"""

from app.services.llm.registry import llm_registry


def test_get_or_default_returns_requested_when_registered() -> None:
    """请求已注册模型时按名返回对应实例。"""
    name = llm_registry.get_all_names()[0]
    llm, resolved = llm_registry.get_or_default(name)
    assert resolved == name
    assert llm is not None


def test_get_or_default_falls_back_on_unknown_model() -> None:
    """请求未注册模型时回退到默认/第一个，而非抛错。"""
    llm, resolved = llm_registry.get_or_default("claude-sonnet-4-5-does-not-exist")
    assert resolved in llm_registry.get_all_names()
    assert llm is not None


def test_get_or_default_handles_empty_name() -> None:
    """名称为空时同样回退到有效模型。"""
    llm, resolved = llm_registry.get_or_default(None)
    assert resolved in llm_registry.get_all_names()
    assert llm is not None
