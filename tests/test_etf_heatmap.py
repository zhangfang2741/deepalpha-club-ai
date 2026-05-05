"""ETF 热力图相关测试。"""
import pytest
from app.schemas.etf import HeatmapCell, HeatmapETFRow, HeatmapSectorGroup, HeatmapResponse
from app.services.etf.fetcher import compute_clv, compute_flow, z_score_normalize, ETF_LIBRARY, CHINESE_NAMES


def test_heatmap_cell_valid():
    cell = HeatmapCell(date="2026-04-24", intensity=1.23)
    assert cell.date == "2026-04-24"
    assert cell.intensity == 1.23


def test_heatmap_cell_allows_none_intensity():
    cell = HeatmapCell(date="2026-04-24", intensity=None)
    assert cell.intensity is None


def test_heatmap_response_structure():
    response = HeatmapResponse(
        granularity="day",
        days=30,
        date_labels=["2026-04-24"],
        sectors=[
            HeatmapSectorGroup(
                sector="01 信息技术",
                avg_cells=[HeatmapCell(date="2026-04-24", intensity=0.5)],
                etfs=[
                    HeatmapETFRow(
                        symbol="XLK",
                        name="科技行业精选指数ETF-SPDR",
                        cells=[HeatmapCell(date="2026-04-24", intensity=1.2)],
                    )
                ],
            )
        ],
    )
    assert response.granularity == "day"
    assert len(response.sectors) == 1
    assert response.sectors[0].etfs[0].symbol == "XLK"


# ── 计算函数测试 ───────────────────────────────────────────────────────────────

def test_compute_clv_mid_range():
    assert compute_clv(adj_close=10.0, high=12.0, low=8.0) == pytest.approx(0.0)


def test_compute_clv_at_high():
    assert compute_clv(adj_close=12.0, high=12.0, low=8.0) == pytest.approx(1.0)


def test_compute_clv_at_low():
    assert compute_clv(adj_close=8.0, high=12.0, low=8.0) == pytest.approx(-1.0)


def test_compute_clv_high_equals_low():
    result = compute_clv(adj_close=10.0, high=10.0, low=10.0)
    assert isinstance(result, float)


def test_compute_flow():
    clv = 0.5
    adj_close = 100.0
    volume = 1_000_000
    assert compute_flow(clv, adj_close, volume) == pytest.approx(50_000_000.0)


def test_z_score_normalize_known_values():
    import math
    flows = [1.0, 2.0, 3.0]
    result = z_score_normalize(flows)
    # 总体标准差 = sqrt(2/3) ≈ 0.8165，z-scores = [-1.2247, 0, 1.2247]
    std = math.sqrt(2 / 3)
    assert result[0] == pytest.approx(-1.0 / std)
    assert result[1] == pytest.approx(0.0)
    assert result[2] == pytest.approx(1.0 / std)


def test_z_score_normalize_constant_returns_zeros():
    flows = [5.0, 5.0, 5.0]
    result = z_score_normalize(flows)
    assert all(r == pytest.approx(0.0) for r in result)


def test_etf_library_has_12_sectors():
    assert len(ETF_LIBRARY) == 12


def test_chinese_names_covers_all_etfs():
    all_symbols = [sym for symbols in ETF_LIBRARY.values() for sym in symbols]
    for sym in all_symbols:
        assert sym in CHINESE_NAMES, f"{sym} 缺少中文名"
