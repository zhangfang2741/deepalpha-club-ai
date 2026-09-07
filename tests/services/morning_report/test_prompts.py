"""prompt 渲染：三市场可渲染、占位符全部替换、市场段落注入。"""

import pytest

from app.services.morning_report.prompts import render_prompt


@pytest.mark.parametrize("market", ["us", "cn", "hk"])
@pytest.mark.parametrize("kind", ["recon", "write"])
def test_render_replaces_all_placeholders(kind, market):
    text = render_prompt(kind, market, "2026-09-08")
    assert "{{" not in text and "}}" not in text
    assert "2026-09-08" in text


def test_write_prompt_contains_core_rules():
    """写作 prompt 必须包含军规关键词（四层结构/时间范围/双语/禁抽象话）。"""
    text = render_prompt("write", "us", "2026-09-08")
    for word in ["事实", "洞察", "预测", "验证", "24-72", "zh", "en", "抽象"]:
        assert word in text


def test_market_block_injected():
    us = render_prompt("write", "us", "2026-09-08")
    cn = render_prompt("write", "cn", "2026-09-08")
    assert "美股" in us and "北向" in cn
