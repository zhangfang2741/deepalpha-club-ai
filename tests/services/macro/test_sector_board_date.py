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


async def test_cn_hk_sector_board_lists_native_sectors_without_strength(monkeypatch):
    from app.services.signal_radar import service as radar_service

    async def fake_counts(redis, market, universe_key):
        return "2026-09-30", {"电子": {"buy": 1, "sell": 2}, "银行": {"buy": 1, "sell": 0}}

    monkeypatch.setattr(radar_service, "latest_sector_counts", fake_counts)
    cn = await svc.get_sector_board(_Redis(), "cn", "zh", None)
    assert cn.available and len(cn.sectors) == 31 and cn.radar_universe == "csi300"
    assert [s.key for s in cn.sectors[:2]] == ["电子", "银行"]  # 有信号的排前面
    assert all(s.rs_vs_market is None and s.label is None and s.name == s.key for s in cn.sectors)
    assert (cn.sectors[0].buy_count, cn.sectors[0].sell_count) == (1, 2)

    hk = await svc.get_sector_board(_Redis(), "hk", "zh", None, date="2026-09-24")
    assert hk.available and len(hk.sectors) == 12 and hk.radar_date is None
    assert all(s.buy_count == 0 for s in hk.sectors)

    # 下钻 / 未知市场仍不可用
    assert not (await svc.get_sector_board(_Redis(), "cn", "zh", "电子")).available
    assert not (await svc.get_sector_board(_Redis(), "jp", "zh", None)).available
