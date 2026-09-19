"""信号雷达的扫描 universe：每个市场提供「科技指数」+「大盘宽基指数」两套。

一个市场（us/cn/hk）下有多个 universe，每个 universe 是一套扫描范围：
- 科技指数（默认，`is_default=True`）：纳斯达克100 / 科创50 / 恒生科技；
- 大盘宽基：标普500 / 沪深300 / 恒生指数（更全的一揽子）。

成分股来源分策略（source）：
- etf_holdings：拉某 ETF 的持仓（FMP，美股覆盖好）；
- fmp_sp500  ：FMP 标普500 成分专用端点（拿全量 ~500）；
- akshare_index：akshare 指数成分（A 股/港股大盘全量，source_arg 为指数代码）；
所有来源失败/覆盖不足时，一律回退到本文件里 curated 的静态清单（constituents），
保证任何情况下都有可扫的范围。静态清单同时用于 detect_market 校验（见单测）。

代码形态遵循 app/utils/market.py 的裸号约定：
- 美股：字母代码（AAPL）
- A 股：6 位数字（688981）
- 港股：4~5 位数字（0700）
"""
from __future__ import annotations

from dataclasses import dataclass

# 成分来源策略
SOURCE_ETF_HOLDINGS = "etf_holdings"
SOURCE_FMP_SP500 = "fmp_sp500"
SOURCE_AKSHARE_INDEX = "akshare_index"

# 科技指数（窄基）默认扫描上限；大盘宽基要「更全」，上限放大。
_TECH_MAX_SCAN = 40
_BROAD_MAX_SCAN = 520


@dataclass(frozen=True)
class MarketUniverse:
    """一个 universe 的扫描配置。"""

    market: str          # us / cn / hk
    key: str             # universe 唯一键（同市场内唯一），如 nasdaq100 / sp500
    etf_name: str        # 展示名（标题里的「恒生科技」等）
    etf_symbol: str      # 参考指数/ETF 代码（展示 + 动态拉成分用）
    constituents: list[tuple[str, str]]  # curated 静态清单 [(裸代码, 中文名), ...]
    is_default: bool = False             # 该市场默认 universe（进页面先看这个）
    source: str = SOURCE_ETF_HOLDINGS    # 成分来源策略
    source_arg: str = ""                 # 来源参数（如 akshare 指数代码 000300）
    max_scan: int = _TECH_MAX_SCAN       # 单 universe 扫描上限（控制扫描时长/数据源压力）


# ── 美股：纳斯达克100（科技，默认）+ 标普500（大盘） ──────────────────────────
_US_NASDAQ100 = MarketUniverse(
    market="us",
    key="nasdaq100",
    etf_name="纳斯达克100",
    etf_symbol="QQQ",
    is_default=True,
    source=SOURCE_ETF_HOLDINGS,
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

_US_SP500 = MarketUniverse(
    market="us",
    key="sp500",
    etf_name="标普500",
    etf_symbol="^GSPC",
    source=SOURCE_FMP_SP500,
    max_scan=_BROAD_MAX_SCAN,
    # 静态兜底：跨行业大盘龙头（FMP 标普500 端点可用时会拿到全量 ~500 覆盖它）。
    constituents=[
        ("AAPL", "苹果"), ("MSFT", "微软"), ("NVDA", "英伟达"), ("AMZN", "亚马逊"),
        ("GOOGL", "谷歌"), ("META", "Meta"), ("TSLA", "特斯拉"), ("AVGO", "博通"),
        ("LLY", "礼来"), ("JPM", "摩根大通"), ("V", "Visa"), ("UNH", "联合健康"),
        ("XOM", "埃克森美孚"), ("MA", "万事达"), ("JNJ", "强生"), ("PG", "宝洁"),
        ("HD", "家得宝"), ("COST", "好市多"), ("ABBV", "艾伯维"), ("WMT", "沃尔玛"),
        ("KO", "可口可乐"), ("PEP", "百事"), ("BAC", "美国银行"), ("MRK", "默克"),
        ("CVX", "雪佛龙"), ("ADBE", "Adobe"), ("CRM", "Salesforce"), ("NFLX", "奈飞"),
        ("AMD", "超微"), ("ACN", "埃森哲"), ("MCD", "麦当劳"), ("LIN", "林德"),
        ("DIS", "迪士尼"), ("WFC", "富国银行"), ("TMO", "赛默飞"), ("ABT", "雅培"),
        ("CSCO", "思科"), ("INTC", "英特尔"), ("QCOM", "高通"), ("TXN", "德州仪器"),
        ("DHR", "丹纳赫"), ("VZ", "威瑞森"), ("PM", "菲莫国际"), ("NKE", "耐克"),
        ("PFE", "辉瑞"), ("IBM", "IBM"), ("GE", "通用电气"), ("CAT", "卡特彼勒"),
        ("HON", "霍尼韦尔"), ("UNP", "联合太平洋"),
    ],
)

# ── A 股：科创50（科技，默认）+ 沪深300（大盘） ──────────────────────────────
_CN_STAR50 = MarketUniverse(
    market="cn",
    key="star50",
    etf_name="科创50",
    etf_symbol="588000",
    is_default=True,
    source=SOURCE_ETF_HOLDINGS,
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

_CN_CSI300 = MarketUniverse(
    market="cn",
    key="csi300",
    etf_name="沪深300",
    etf_symbol="000300",
    source=SOURCE_AKSHARE_INDEX,
    source_arg="000300",
    max_scan=_BROAD_MAX_SCAN,
    # 静态兜底：沪深两市各行业大盘龙头（akshare 可用时拿全量 300 覆盖它）。
    constituents=[
        ("600519", "贵州茅台"), ("300750", "宁德时代"), ("601318", "中国平安"),
        ("600036", "招商银行"), ("000858", "五粮液"), ("601899", "紫金矿业"),
        ("600900", "长江电力"), ("000333", "美的集团"), ("002594", "比亚迪"),
        ("601166", "兴业银行"), ("600030", "中信证券"), ("000001", "平安银行"),
        ("600276", "恒瑞医药"), ("601288", "农业银行"), ("600887", "伊利股份"),
        ("601398", "工商银行"), ("601988", "中国银行"), ("600000", "浦发银行"),
        ("601601", "中国太保"), ("601668", "中国建筑"), ("600028", "中国石化"),
        ("601857", "中国石油"), ("000651", "格力电器"), ("002415", "海康威视"),
        ("600309", "万华化学"), ("601012", "隆基绿能"), ("600585", "海螺水泥"),
        ("000725", "京东方A"), ("002304", "洋河股份"), ("600690", "海尔智家"),
        ("601728", "中国电信"), ("600050", "中国联通"), ("601088", "中国神华"),
        ("603259", "药明康德"), ("600438", "通威股份"), ("601211", "国泰海通"),
        ("000568", "泸州老窖"), ("002714", "牧原股份"), ("600031", "三一重工"),
        ("601633", "长城汽车"), ("300059", "东方财富"), ("600809", "山西汾酒"),
        ("601066", "中信建投"), ("000002", "万科A"), ("600104", "上汽集团"),
    ],
)

# ── 港股：恒生科技（科技，默认）+ 恒生指数（大盘） ──────────────────────────
_HK_HSTECH = MarketUniverse(
    market="hk",
    key="hstech",
    etf_name="恒生科技",
    etf_symbol="3033",
    is_default=True,
    source=SOURCE_ETF_HOLDINGS,
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

_HK_HSI = MarketUniverse(
    market="hk",
    key="hsi",
    etf_name="恒生指数",
    etf_symbol="2800",
    source=SOURCE_AKSHARE_INDEX,
    source_arg="HSI",
    max_scan=_BROAD_MAX_SCAN,
    # 静态兜底/主用：恒生指数蓝筹（akshare 港股指数成分覆盖不稳定时以此为准）。
    constituents=[
        ("0700", "腾讯控股"), ("0005", "汇丰控股"), ("9988", "阿里巴巴"),
        ("1299", "友邦保险"), ("0939", "建设银行"), ("0941", "中国移动"),
        ("1398", "工商银行"), ("3690", "美团"), ("0388", "香港交易所"),
        ("0883", "中国海洋石油"), ("1810", "小米集团"), ("2318", "中国平安"),
        ("0016", "新鸿基地产"), ("0011", "恒生银行"), ("2628", "中国人寿"),
        ("1109", "华润置地"), ("0001", "长和"), ("0002", "中电控股"),
        ("0003", "香港中华煤气"), ("0006", "电能实业"), ("0012", "恒基地产"),
        ("0027", "银河娱乐"), ("0066", "港铁公司"), ("0101", "恒隆地产"),
        ("0175", "吉利汽车"), ("0267", "中信股份"), ("0288", "万洲国际"),
        ("0386", "中国石油化工"), ("0688", "中国海外发展"), ("0762", "中国联通"),
        ("0823", "领展房产基金"), ("0857", "中国石油股份"), ("0868", "信义玻璃"),
        ("0960", "龙湖集团"), ("0968", "信义光能"), ("1038", "长江基建"),
        ("1088", "中国神华"), ("1113", "长实集团"), ("1177", "中国生物制药"),
        ("1211", "比亚迪股份"), ("1876", "百威亚太"), ("1928", "金沙中国"),
        ("2020", "安踏体育"), ("2269", "药明生物"), ("2313", "申洲国际"),
        ("2331", "李宁"), ("2382", "舜宇光学"), ("3328", "交通银行"),
        ("9618", "京东集团"), ("9999", "网易"),
    ],
)


_ALL_UNIVERSES: list[MarketUniverse] = [
    _US_NASDAQ100, _US_SP500, _CN_STAR50, _CN_CSI300, _HK_HSTECH, _HK_HSI,
]

# 按市场分组（保留声明顺序，默认在前），及 (market, key) 精确索引。
_BY_MARKET: dict[str, list[MarketUniverse]] = {}
_BY_KEY: dict[tuple[str, str], MarketUniverse] = {}
for _u in _ALL_UNIVERSES:
    _BY_MARKET.setdefault(_u.market, []).append(_u)
    _BY_KEY[(_u.market, _u.key)] = _u
# 默认 universe 排在各市场列表最前，保证 list_universes / 默认选择稳定。
for _m, _lst in _BY_MARKET.items():
    _lst.sort(key=lambda u: (not u.is_default))


def get_universe(market: str, key: str | None = None) -> MarketUniverse | None:
    """按市场 + universe 键取扫描配置。

    key 为 None 时返回该市场的默认（科技指数）universe；市场或 key 未知返回 None。
    """
    if key is None:
        candidates = _BY_MARKET.get(market)
        if not candidates:
            return None
        for u in candidates:
            if u.is_default:
                return u
        return candidates[0]
    return _BY_KEY.get((market, key))


def list_universes(market: str) -> list[MarketUniverse]:
    """某市场可选的全部 universe（默认在前），未知市场返回空列表。"""
    return list(_BY_MARKET.get(market, []))


def all_universes() -> list[MarketUniverse]:
    """全部 (market, universe)，供后台预热遍历。"""
    return list(_ALL_UNIVERSES)


def supported_markets() -> list[str]:
    """支持的市场列表。"""
    return list(_BY_MARKET.keys())
