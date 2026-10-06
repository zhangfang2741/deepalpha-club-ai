"""财报中文要点：章节挑选、可读性判断、措辞过滤、缓存 / 锁 / 每日上限流程。"""

from __future__ import annotations

import asyncio

import pytest

from app.schemas.quant_research import LatestReportOut, ReportKeyNumber, ReportSummary
from app.services.quant_research import report_summary as rs
from app.services.quant_research import report_text as rt


def _page(*lines: str) -> str:
    return "\n".join(lines)


def test_pick_pdf_sections_skips_toc_and_stops_at_next_chapter():
    pages = [
        _page("封面"),
        _page("目录", "第一节 释义", "第二节 财务概要", "第三节 管理层讨论与分析", "第四节 公司治理"),
        _page("第二节 财务概要", "营业收入 489.5 亿元"),
        _page("续表"),
        _page("第三节 管理层讨论与分析", "报告期内公司经营情况良好" * 5),
        _page("经营数据" * 10),
        _page("第四节 公司治理", "董事会情况"),
        _page("不应出现的内容"),
    ]
    out = rt.pick_pdf_sections(pages)
    assert "营业收入 489.5 亿元" in out and "报告期内公司经营情况" in out and "经营数据" in out
    assert "董事会情况" not in out and "不应出现的内容" not in out


def test_pick_pdf_sections_falls_back_to_front_pages():
    pages = ["封面"] + [f"第{i}页正文" for i in range(1, 20)]
    out = rt.pick_pdf_sections(pages)
    assert "第1页正文" in out and "第19页正文" not in out


def test_us_sections_prefers_longest_mda_over_toc_entry():
    toc = "Item 2. Management’s Discussion and Analysis of Financial Condition\nItem 3. Quantitative and Qualitative Disclosures\n"
    body = "Item 2. Management’s Discussion and Analysis of Financial Condition\n" + "Revenue grew strongly. " * 200 + "\nItem 3. Quantitative and Qualitative Disclosures\nlater"
    out = rt.us_sections(toc + body, "10-Q")
    assert "Revenue grew strongly" in out and "later" not in out


def test_looks_readable_rejects_garbled_and_short():
    assert rt.looks_readable("营业收入同比增长百分之九，净利润保持稳定。Revenue 123 " * 40)
    assert not rt.looks_readable("ͦ፽ࣘజѓڌرً" * 200)
    assert not rt.looks_readable("太短")


def test_sanitize_drops_trade_wording_and_limits():
    s = ReportSummary(headline="营收增长", key_numbers=[ReportKeyNumber(label="营收", value="100 亿元", change="+9%"),
                                                       ReportKeyNumber(label="", value="x")],
                      highlights=["收入增长 9%", "建议买入这只股票", "利润稳定"], watch_points=["目标价 100 元"],
                      outlook="强烈推荐持有")
    out = rs.sanitize(s)
    assert [n.label for n in out.key_numbers] == ["营收"]
    assert out.highlights == ["收入增长 9%", "利润稳定"] and out.watch_points == [] and out.outlook == ""


class FakeRedis:
    def __init__(self):
        self.kv: dict = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, ex=None, nx=False):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def delete(self, k):
        self.kv.pop(k, None)

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k, ttl):
        return True


REPORT = LatestReportOut(status="ok", symbol="600150", title="t", report_type="中报", filed_date="2026-08-31",
                         url="https://pdf.dfcfw.com/pdf/H2_AN1_1.pdf", file_type="pdf")


@pytest.fixture
def patched(monkeypatch):
    async def fake_report(*a, **k):
        return REPORT

    async def fake_extract(report):
        return "正文" * 400

    calls = {"llm": 0}

    async def fake_summarize(text, report, lang):
        calls["llm"] += 1
        return ReportSummary(headline="营收稳健", highlights=["a"])

    monkeypatch.setattr(rs, "get_latest_report", fake_report)
    monkeypatch.setattr(rs, "_extract_text", fake_extract)
    monkeypatch.setattr(rs, "summarize_text", fake_summarize)
    monkeypatch.setattr(rs.settings, "REPORT_SUMMARY_ENABLED", True)
    return calls


async def _wait_ready(redis, tries=50):
    for _ in range(tries):
        out = await rs.get_report_summary("cn", "600150", "zh", redis=redis)
        if out.status != "generating":
            return out
        await asyncio.sleep(0.01)
    raise AssertionError("still generating")


async def test_generate_then_cache_hit_calls_llm_once(patched):
    redis = FakeRedis()
    first = await rs.get_report_summary("cn", "600150", "zh", redis=redis)
    assert first.status == "generating"
    done = await _wait_ready(redis)
    assert done.status == "ready" and done.summary.headline == "营收稳健" and done.note
    again = await rs.get_report_summary("cn", "600150", "zh", redis=redis)
    assert again.status == "ready" and patched["llm"] == 1


async def test_daily_limit_blocks_new_generation(patched, monkeypatch):
    monkeypatch.setattr(rs.settings, "REPORT_SUMMARY_DAILY_LIMIT", 0)
    out = await rs.get_report_summary("cn", "600150", "zh", redis=FakeRedis())
    assert out.status == "limit_reached" and patched["llm"] == 0


async def test_unreadable_text_is_reported_not_retried(patched, monkeypatch):
    async def empty(report):
        return ""

    monkeypatch.setattr(rs, "_extract_text", empty)
    redis = FakeRedis()
    await rs.get_report_summary("cn", "600150", "zh", redis=redis)
    out = await _wait_ready(redis)
    assert out.status == "unavailable" and "无法提取" in (out.note or "") and patched["llm"] == 0


async def test_disabled(monkeypatch):
    monkeypatch.setattr(rs.settings, "REPORT_SUMMARY_ENABLED", False)
    assert (await rs.get_report_summary("cn", "600150", "zh", redis=FakeRedis())).status == "disabled"
