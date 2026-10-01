"""行业弹层按日期：雷达翻到哪天，行业强弱就取那天收盘（不晚于该日的最近交易日）。"""
from app.services.macro import regime_view
from app.services.macro import service as svc
from app.services.macro.regime_view import SectorRow


class _Redis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


async def test_sector_board_reads_rows_as_of_requested_date(monkeypatch):
    calls: list = []

    def load(parent=None, as_of=None):
        calls.append((parent, as_of))
        return [SectorRow(as_of or "2026-09-30", "energy", 0.02, "risk_on", None, 0.6),
                SectorRow(as_of or "2026-09-30", "technology", 0.05, "risk_on", None, 0.7)]

    monkeypatch.setattr(regime_view, "load_sector_rows", load)
    redis = _Redis()
    resp = await svc.get_sector_board(redis, "us", "zh", None, date="2026-09-24")
    assert calls == [(None, "2026-09-24")]
    assert resp.as_of == "2026-09-24"
    assert [s.key for s in resp.sectors] == ["technology", "energy"]
    # 不同日期分开缓存；同一日期命中缓存不再查库
    await svc.get_sector_board(redis, "us", "zh", None, date="2026-09-24")
    await svc.get_sector_board(redis, "us", "zh", None, date="2026-09-23")
    assert calls == [(None, "2026-09-24"), (None, "2026-09-23")]
