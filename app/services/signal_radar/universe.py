"""信号雷达的扫描universe：各市场科技 ETF 的代表性成分股。

每个市场对应一只「科技 ETF」，取其代表性成分股作为每日缠论扫描范围。
成分股清单是 curated 快照（非实时权重），后续可接 FMP/交易所成分接口动态刷新；
现阶段静态维护即可，重点是把扫描范围与展示名称固定下来。

代码形态遵循 app/utils/market.py 的裸号约定：
- 美股：字母代码（AAPL）
- A 股：6 位数字（688981）
- 港股：4~5 位数字（0700）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketUniverse:
    """一个市场的扫描配置。"""

    market: str          # us / cn / hk
    etf_name: str        # 展示用 ETF 名称
    etf_symbol: str      # 参考 ETF 代码（展示/未来拉权重用）
    constituents: list[tuple[str, str]]  # [(symbol, 中文名), ...]


# 美股：纳斯达克 100 里的科技/通信龙头（QQQ 科技权重核心）
_US = MarketUniverse(
    market="us",
    etf_name="纳斯达克100",
    etf_symbol="QQQ",
    constituents=[
        ("NVDA", "英伟达"), ("AAPL", "苹果"), ("MSFT", "微软"), ("AVGO", "博通"),
        ("AMD", "超微"), ("TSLA", "特斯拉"), ("META", "Meta"), ("GOOGL", "谷歌"),
        ("AMZN", "亚马逊"), ("NFLX", "奈飞"), ("ADBE", "Adobe"), ("QCOM", "高通"),
        ("INTC", "英特尔"), ("MU", "美光"), ("PANW", "Palo Alto"), ("CRWD", "CrowdStrike"),
        ("ASML", "阿斯麦"), ("AMAT", "应用材料"), ("LRCX", "泛林"), ("KLAC", "科天"),
        ("ADI", "亚德诺"), ("TXN", "德州仪器"), ("MRVL", "美满电子"), ("NXPI", "恩智浦"),
        ("SNPS", "新思科技"), ("CDNS", "楷登电子"), ("INTU", "Intuit"), ("CSCO", "思科"),
        ("ARM", "Arm"), ("PLTR", "Palantir"), ("DDOG", "Datadog"), ("TEAM", "Atlassian"),
        ("FTNT", "Fortinet"), ("ZS", "Zscaler"), ("APP", "AppLovin"),
    ],
)

# A 股：科创 50（科创板龙头，代码多为 688 开头，另含少量科技权重股）
_CN = MarketUniverse(
    market="cn",
    etf_name="科创50",
    etf_symbol="588000",
    constituents=[
        ("688981", "中芯国际"), ("688111", "金山办公"), ("688012", "中微公司"),
        ("688008", "澜起科技"), ("688169", "石头科技"), ("688036", "传音控股"),
        ("688396", "华润微"), ("688271", "联影医疗"), ("688187", "时代电气"),
        ("688516", "奥特维"), ("688041", "海光信息"), ("688126", "沪硅产业"),
        ("688256", "寒武纪"), ("688009", "中国通号"), ("688223", "晶科能源"),
        ("688303", "大全能源"), ("688599", "天合光能"), ("688180", "君实生物"),
        ("688202", "美迪西"), ("688561", "奇安信"), ("688521", "芯原股份"),
        ("688082", "盛美上海"), ("688385", "复旦微电"), ("688063", "派能科技"),
        ("688157", "松井股份"), ("688072", "拓荆科技"), ("688347", "华虹公司"),
        ("688728", "格科微"), ("603501", "韦尔股份"),
    ],
)

# 港股：恒生科技（互联网 + 硬科技龙头）
_HK = MarketUniverse(
    market="hk",
    etf_name="恒生科技",
    etf_symbol="3033",
    constituents=[
        ("0700", "腾讯控股"), ("9988", "阿里巴巴"), ("3690", "美团"),
        ("1810", "小米集团"), ("9618", "京东集团"), ("9999", "网易"),
        ("1024", "快手"), ("9868", "小鹏汽车"), ("2015", "理想汽车"),
        ("0981", "中芯国际"), ("2382", "舜宇光学"), ("0020", "商汤"),
        ("9626", "哔哩哔哩"), ("9888", "百度集团"), ("1347", "华虹半导体"),
        ("0992", "联想集团"), ("0285", "比亚迪电子"), ("6618", "京东健康"),
        ("2269", "药明生物"), ("9866", "蔚来"), ("9961", "携程集团"),
        ("3888", "金山软件"), ("0268", "金蝶国际"), ("1833", "平安好医生"),
        ("6060", "众安在线"), ("9698", "万国数据"),
    ],
)

_UNIVERSES: dict[str, MarketUniverse] = {u.market: u for u in (_US, _CN, _HK)}


def get_universe(market: str) -> MarketUniverse | None:
    """按市场取扫描配置，未知市场返回 None。"""
    return _UNIVERSES.get(market)


def supported_markets() -> list[str]:
    """支持的市场列表。"""
    return list(_UNIVERSES.keys())
