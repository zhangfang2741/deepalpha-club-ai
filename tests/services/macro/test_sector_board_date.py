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


async def test_cn_hk_sector_board_lists_native_sectors_with_strength_when_available(monkeypatch):
    from app.services.signal_radar import service as radar_service

    async def fake_counts(redis, market, universe_key):
        return "2026-09-30", {"电子": {"buy": 1, "sell": 2}, "银行": {"buy": 1, "sell": 0}}

    asked: list = []

    def load(market, as_of=None):
        asked.append((market, as_of))
        return [SectorRow("2026-09-30", "银行", 0.058, "risk_on", "risk_on", 0.9),
                SectorRow("2026-09-30", "煤炭", -0.016, "risk_off", "risk_off", 0.0)]

    monkeypatch.setattr(radar_service, "latest_sector_counts", fake_counts)
    monkeypatch.setattr(regime_view, "load_market_sector_rows", load)
    cn = await svc.get_sector_board(_Redis(), "cn", "zh", None)
    assert cn.available and len(cn.sectors) == 31 and cn.radar_universe == "csi300" and cn.as_of == "2026-09-30"
    # 有强弱的排前面（从强到弱），其后没有强弱的按买卖点合计排
    assert [s.key for s in cn.sectors[:3]] == ["银行", "煤炭", "电子"]
    bank = cn.sectors[0]
    assert bank.rs_vs_market == 0.058 and bank.label == "risk_on" and bank.buy_count == 1
    assert all(s.rs_vs_market is None for s in cn.sectors[2:]) and all(s.name == s.key for s in cn.sectors)

    hk = await svc.get_sector_board(_Redis(), "hk", "zh", None, date="2026-09-24")
    assert hk.available and len(hk.sectors) == 12 and hk.radar_date is None
    assert asked[-1] == ("hk", "2026-09-24")

    # 下钻 / 未知市场仍不可用
    assert not (await svc.get_sector_board(_Redis(), "cn", "zh", "电子")).available
    assert not (await svc.get_sector_board(_Redis(), "jp", "zh", None)).available


async def test_cn_hk_sector_board_without_state_rows_still_lists_sectors(monkeypatch):
    monkeypatch.setattr(regime_view, "load_market_sector_rows", lambda market, as_of=None: [])
    cn = await svc.get_sector_board(_Redis(), "cn", "zh", None, date="2026-09-24")
    assert cn.available and cn.as_of is None and len(cn.sectors) == 31
    assert all(s.rs_vs_market is None for s in cn.sectors)


async def test_cn_hk_macro_has_state_but_no_drivers(monkeypatch):
    rows = [regime_view.StateRow("2026-09-29", "risk_on", "risk_on", 0.7, 0.2, 0.1),
            regime_view.StateRow("2026-09-30", "neutral", "neutral", 0.2, 0.7, 0.1)]
    seen: list = []

    def load(limit=260, market="us"):
        seen.append(market)
        return rows

    async def calendar(redis):
        return []

    monkeypatch.setattr(regime_view, "load_state_rows", load)
    monkeypatch.setattr(regime_view, "load_market_sector_rows", lambda market, as_of=None: [
        SectorRow("2026-09-30", "银行", 0.05, "risk_on", "risk_on", 0.8),
        SectorRow("2026-09-30", "煤炭", -0.02, "risk_off", "risk_off", 0.1)])
    monkeypatch.setattr(svc, "_calendar", calendar)
    for market in ("cn", "hk"):
        resp = await svc.get_macro(_Redis(), market, "zh")
        assert resp.available and resp.state is not None and resp.state.label == "neutral"
        assert resp.drivers == [] and len(resp.history) == 2
    assert seen == ["cn", "hk"]

    overview = await svc.get_overview(_Redis(), "cn", "zh")
    assert overview.available and overview.macro_state is not None
    assert overview.strongest is not None and overview.strongest.name == "银行"
    assert overview.weakest is not None and overview.weakest.name == "煤炭"

    # 没有大盘状态的市场仍不可用
    assert not (await svc.get_macro(_Redis(), "jp", "zh")).available
    assert not (await svc.get_overview(_Redis(), "jp", "zh")).available


async def test_cn_macro_before_first_run_is_available_but_empty(monkeypatch):
    async def calendar(redis):
        return []

    monkeypatch.setattr(regime_view, "load_state_rows", lambda limit=260, market="us": [])
    monkeypatch.setattr(svc, "_calendar", calendar)
    resp = await svc.get_macro(_Redis(), "cn", "zh")
    assert resp.available and resp.state is None  # App 显示「数据准备中」（等第一轮计算）
