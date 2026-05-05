"""ETF 热力图相关测试。"""
import pytest
from app.schemas.etf import HeatmapCell, HeatmapETFRow, HeatmapSectorGroup, HeatmapResponse


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
