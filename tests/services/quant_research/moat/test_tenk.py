"""10-K Item 1 截取：避开目录与每页页眉，找不到标准标题时退回关键词段落。"""

from app.services.quant_research.moat.tenk import extract_business

BODY = "Overview. We operate the largest payments network. " * 100
REG = "Regulation. Privacy laws apply to our business in many countries. " * 60


def _html(*parts: str) -> str:
    return "<html><body>" + "".join(f"<p>{p}</p>" for p in parts) + "</body></html>"


def test_takes_body_section_not_table_of_contents():
    html = _html("Item 1.", "Business", "Item 1A.", "Risk Factors",  # 目录
                 "ITEM 1. BUSINESS", BODY, "ITEM 1A. RISK FACTORS", "We face risks. " * 50)
    out = extract_business(html)
    assert out is not None and out.startswith("ITEM 1. BUSINESS") and "largest payments network" in out
    assert "We face risks" not in out


def test_repeated_page_headers_do_not_truncate_to_last_page():
    """每页页眉都印「ITEM 1. BUSINESS」时，要从第一个开始截，而不是最后一个。"""
    html = _html("ITEM 1. BUSINESS", BODY, "ITEM 1. BUSINESS", REG, "ITEM 1A. RISK FACTORS", "x " * 10)
    out = extract_business(html)
    assert out is not None and "largest payments network" in out and "Privacy laws" in out


def test_keyword_fallback_for_non_standard_filings():
    paras = ["Our competitive position depends on our brand and patents. " * 5] * 20
    out = extract_business(_html("Annual report", *paras, "tail " * 2000))
    assert out is not None and "competitive position" in out


def test_none_when_nothing_usable():
    assert extract_business(_html("Nothing here.")) is None
