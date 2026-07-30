"""市场状态监控（regime）模块常量。

三篮子（对应「资金像水，逐利/避险」直觉）：
- OFFENSE 进攻篮子：科技/半导体/可选消费/工业 —— 逐利时资金涌入。
- DEFENSE 防御篮子：公用事业/必需消费/医疗 —— 避险时资金流入。
- CASH 现金篮子：短端国债 ETF —— 整体离场时资金停泊。
"""
from __future__ import annotations

# 三篮子成分（等权）
OFFENSE_BASKET: list[str] = ["XLK", "XLY", "XLI", "SMH"]
DEFENSE_BASKET: list[str] = ["XLU", "XLP", "XLV"]
CASH_BASKET: list[str] = ["BIL", "SHV"]

# 纳指与波动率代理
NASDAQ_SYMBOL = "QQQ"
VIX_SYMBOL = "^VIX"

# 滚动窗口参数（统一用滚动窗口，不用 rebase-since-基准日）
RS_WINDOW = 20  # 篮子相对强弱回看窗口（交易日）
RETURN_WINDOW = 20  # 纳指动量窗口
VOL_WINDOW = 20  # 已实现波动窗口
OBV_CMF_WINDOW = 20  # OBV 斜率 / CMF 窗口

TRADING_DAYS = 252  # 年化因子

# HMM 状态与标签
N_STATES = 3
LABEL_RISK_ON = "risk_on"  # 逐利
LABEL_NEUTRAL = "neutral"  # 观望
LABEL_RISK_OFF = "risk_off"  # 避险

STATE_LABELS = [LABEL_RISK_ON, LABEL_NEUTRAL, LABEL_RISK_OFF]

LABEL_ZH = {
    LABEL_RISK_ON: "逐利",
    LABEL_NEUTRAL: "观望",
    LABEL_RISK_OFF: "避险",
}

# ── 行业（板块）级 regime ──────────────────────────────────────
# 市场基准（板块相对强弱 RS 的对标）
MARKET_SYMBOL = "SPY"

# 11 个 GICS 行业 SPDR ETF：key（英文标识）/ symbol / 中文名
SECTORS: list[dict[str, str]] = [
    {"key": "technology", "symbol": "XLK", "name": "科技"},
    {"key": "semiconductors", "symbol": "SMH", "name": "半导体"},
    {"key": "discretionary", "symbol": "XLY", "name": "可选消费"},
    {"key": "communication", "symbol": "XLC", "name": "通讯服务"},
    {"key": "financials", "symbol": "XLF", "name": "金融"},
    {"key": "industrials", "symbol": "XLI", "name": "工业"},
    {"key": "energy", "symbol": "XLE", "name": "能源"},
    {"key": "materials", "symbol": "XLB", "name": "材料"},
    {"key": "healthcare", "symbol": "XLV", "name": "医疗"},
    {"key": "staples", "symbol": "XLP", "name": "必需消费"},
    {"key": "utilities", "symbol": "XLU", "name": "公用事业"},
    {"key": "realestate", "symbol": "XLRE", "name": "房地产"},
]

SECTOR_NAME_ZH: dict[str, str] = {s["key"]: s["name"] for s in SECTORS}
SECTOR_SYMBOL: dict[str, str] = {s["key"]: s["symbol"] for s in SECTORS}

# 子行业（细分）ETF：仅在有干净流动品种的一级行业下挂细分。parent 指向 SECTORS.key。
# 半导体/必需消费/公用事业无合适细分 ETF，故不挂子行业。
SUB_INDUSTRIES: list[dict[str, str]] = [
    # 科技
    {"key": "tech_software", "symbol": "IGV", "name": "软件", "parent": "technology"},
    {"key": "tech_cyber", "symbol": "CIBR", "name": "网络安全", "parent": "technology"},
    {"key": "tech_cloud", "symbol": "SKYY", "name": "云计算", "parent": "technology"},
    {"key": "tech_semis", "symbol": "SOXX", "name": "半导体", "parent": "technology"},
    # 可选消费
    {"key": "disc_retail", "symbol": "XRT", "name": "零售", "parent": "discretionary"},
    {"key": "disc_homebuild", "symbol": "ITB", "name": "住宅建筑", "parent": "discretionary"},
    {"key": "disc_leisure", "symbol": "PEJ", "name": "休闲娱乐", "parent": "discretionary"},
    # 通讯服务
    {"key": "comm_social", "symbol": "SOCL", "name": "社交媒体", "parent": "communication"},
    {"key": "comm_gaming", "symbol": "ESPO", "name": "游戏电竞", "parent": "communication"},
    {"key": "comm_internet", "symbol": "FDN", "name": "互联网", "parent": "communication"},
    # 金融
    {"key": "fin_banks", "symbol": "KBE", "name": "银行", "parent": "financials"},
    {"key": "fin_regional", "symbol": "KRE", "name": "区域银行", "parent": "financials"},
    {"key": "fin_insurance", "symbol": "KIE", "name": "保险", "parent": "financials"},
    {"key": "fin_brokers", "symbol": "IAI", "name": "券商资管", "parent": "financials"},
    # 工业
    {"key": "ind_defense", "symbol": "ITA", "name": "航空国防", "parent": "industrials"},
    {"key": "ind_transport", "symbol": "IYT", "name": "运输", "parent": "industrials"},
    # 能源
    {"key": "energy_ep", "symbol": "XOP", "name": "油气开采", "parent": "energy"},
    {"key": "energy_services", "symbol": "OIH", "name": "油服", "parent": "energy"},
    {"key": "energy_clean", "symbol": "ICLN", "name": "清洁能源", "parent": "energy"},
    # 材料
    {"key": "mat_metals", "symbol": "XME", "name": "金属矿业", "parent": "materials"},
    {"key": "mat_gold", "symbol": "GDX", "name": "黄金矿业", "parent": "materials"},
    {"key": "mat_lithium", "symbol": "LIT", "name": "锂电", "parent": "materials"},
    # 医疗
    {"key": "hc_biotech", "symbol": "XBI", "name": "生物科技", "parent": "healthcare"},
    {"key": "hc_devices", "symbol": "IHI", "name": "医疗器械", "parent": "healthcare"},
    {"key": "hc_pharma", "symbol": "PPH", "name": "制药", "parent": "healthcare"},
    # 房地产
    {"key": "re_residential", "symbol": "REZ", "name": "住宅REIT", "parent": "realestate"},
    {"key": "re_mortgage", "symbol": "REM", "name": "抵押REIT", "parent": "realestate"},
]

# 一级行业条目（parent=None）
TOP_LEVEL_ENTRIES: list[dict[str, str | None]] = [
    {"key": s["key"], "symbol": s["symbol"], "name": s["name"], "parent": None}
    for s in SECTORS
]

# 所有可跑 regime 的条目（一级行业 + 子行业）
ALL_SECTOR_ENTRIES: list[dict[str, str | None]] = TOP_LEVEL_ENTRIES + [
    dict(s) for s in SUB_INDUSTRIES  # type: ignore[misc]
]

SECTOR_NAME_ZH.update({s["key"]: s["name"] for s in SUB_INDUSTRIES})
SECTOR_PARENT: dict[str, str] = {s["key"]: s["parent"] for s in SUB_INDUSTRIES}
# 每个一级行业有哪些子行业 key / 子行业条目
SECTOR_CHILDREN: dict[str, list[str]] = {}
SUBINDUSTRY_BY_PARENT: dict[str, list[dict[str, str | None]]] = {}
for _s in SUB_INDUSTRIES:
    SECTOR_CHILDREN.setdefault(_s["parent"], []).append(_s["key"])
    SUBINDUSTRY_BY_PARENT.setdefault(_s["parent"], []).append(dict(_s))  # type: ignore[arg-type]

# 拟合所需最小历史（交易日）——不足则不产出状态标签，避免小样本乱拟合
MIN_FIT_HISTORY = 252

# 「持续 N 日」标签：连续处于同一 regime 达到该天数才算确认
PERSIST_N_DAYS = 3

# 后验退火参数：抑制高斯 HMM 滤波后验饱和成硬 0/1，让 factor_weight 成为平滑旋钮。
# 直觉：对角高斯假设 5 个特征相互独立，但 ODS/波动/VIX 日频高度自相关，
# 5 维似然连乘会把「其实约 1 份独立证据」当成 5 份，后验被压成硬 0/1。
# 温度 T 把每日发射证据退火回约 1 维量级，收缩+转移封顶进一步抑制过度自信。
COVAR_SHRINKAGE = 0.35  # 协方差向池化方差收缩系数 λ
MAX_SELF_TRANSITION = 0.90  # 自转移概率上限，掐断逐日复利式钉死
POSTERIOR_TEMPERATURE = 6.0  # 发射对数似然退火温度 T（≥1）
