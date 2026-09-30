"""标普1500 成分解析与板块映射。"""

from app.services.quant_research.universe import FMP_SECTOR_TO_GICS, GICS_SECTORS, parse_sp_table, sector_name

HTML = """
<table id="constituents"><thead><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr></thead>
<tbody>
<tr><td>NVDA</td><td>Nvidia</td><td>Information Technology</td><td>Semiconductors</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
<tr><td>https://www-nyse-com/quote/XASE:PRK</td><td>Park National</td><td>Financials</td><td>Banks</td></tr>
<tr><td>ZZZ</td><td>Unknown Co</td><td>Not A Sector</td><td>x</td></tr>
</tbody></table>
"""


def test_parse_sp_table_filters_and_maps():
    rows = parse_sp_table(HTML)
    assert rows == [("NVDA", "Nvidia", "information_technology"), ("BRK-B", "Berkshire Hathaway", "financials")]


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
