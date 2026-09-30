"""标普500与纳斯达克100成分解析及板块映射。"""

from app.services.quant_research.universe import (
    FMP_SECTOR_TO_GICS,
    GICS_SECTORS,
    parse_nasdaq100_table,
    parse_sp_table,
    sector_name,
)

HTML = """
<table id="constituents"><thead><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr></thead>
<tbody>
<tr><td>NVDA</td><td>Nvidia</td><td>Information Technology</td><td>Semiconductors</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
<tr><td>https://www-nyse-com/quote/XASE:PRK</td><td>Park National</td><td>Financials</td><td>Banks</td></tr>
<tr><td>ZZZ</td><td>Unknown Co</td><td>Not A Sector</td><td>x</td></tr>
</tbody></table>
"""

NASDAQ_HTML = """
<table><thead><tr><th>Ticker</th><th>Company</th><th>ICB Industry[1]</th><th>ICB Subsector[1]</th></tr></thead>
<tbody>
<tr><td>NVDA</td><td>Nvidia</td><td>Technology</td><td>Semiconductors</td></tr>
<tr><td>AMGN</td><td>Amgen</td><td>Health Care</td><td>Biotechnology</td></tr>
<tr><td>CMCSA</td><td>Comcast</td><td>Telecommunications</td><td>Telecommunications Service Providers</td></tr>
</tbody></table>
"""


def test_parse_sp_table_filters_and_maps():
    rows = parse_sp_table(HTML)
    assert rows == [("NVDA", "Nvidia", "information_technology"), ("BRK-B", "Berkshire Hathaway", "financials")]


def test_parse_nasdaq100_table_maps_icb_industry_to_gics():
    assert parse_nasdaq100_table(NASDAQ_HTML) == [
        ("NVDA", "Nvidia", "information_technology"),
        ("AMGN", "Amgen", "health_care"),
        ("CMCSA", "Comcast", "communication_services"),
    ]


def test_quant_universe_targets_sp500_and_nasdaq100():
    from app.services.quant_research import universe

    assert set(universe.WIKI_PAGES) == {"sp500", "nasdaq100"}


def test_fmp_sector_mapping_covers_all_gics():
    assert set(FMP_SECTOR_TO_GICS.values()) == set(GICS_SECTORS)


def test_sector_name():
    assert sector_name("information_technology", "zh") == "信息技术"
    assert sector_name("health_care", "en") == "Health Care"


def test_real_wiki_page_parses_if_cached():
    import pathlib
    p = pathlib.Path("/tmp/wiki400.html")
    if p.exists():
        rows = parse_sp_table(p.read_text())
        assert len(rows) > 380
