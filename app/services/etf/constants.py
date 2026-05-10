"""ETF 数据集常量定义。"""

from typing import Dict, List

# ETF 中文名称映射
CHINESE_NAMES: Dict[str, str] = {
    "XLK": "科技行业精选指数ETF-SPDR",
    "SOXX": "iShares半导体指数ETF",
    "AIQ": "Global X人工智能与科技ETF",
    "SKYY": "First Trust云计算指数ETF",
    "QTUM": "Defiance量子计算与机器学习ETF",
    "BUG": "Global X网络安全指数ETF",
    "IGV": "iShares扩张科技软件行业ETF",
    "XLV": "医疗保健行业精选指数ETF-SPDR",
    "XHE": "SPDR标普健康医疗设备ETF",
    "IHF": "iShares美国医疗保健提供商ETF",
    "XBI": "SPDR标普生物技术ETF",
    "PJP": "Invesco动力制药ETF",
    "XLF": "金融行业精选指数ETF-SPDR",
    "KBE": "SPDR标普银行指数ETF",
    "IYG": "iShares美国金融服务ETF",
    "KIE": "SPDR标普保险ETF",
    "BLOK": "Amplify转型数据共享ETF(区块链)",
    "KCE": "SPDR标普资本Market ETF",
    "REM": "iShares抵押贷款地产投资信托ETF",
    "XLY": "可选消费行业精选指数ETF-SPDR",
    "CARZ": "First Trust纳斯达克全球汽车指数ETF",
    "XRT": "SPDR标普零售业ETF",
    "XHB": "SPDR标普家居建设ETF",
    "PEJ": "Invesco休闲娱乐ETF",
    "XLP": "必需消费行业精选指数ETF-SPDR",
    "PBJ": "Invesco动力食品饮料ETF",
    "MOO": "VanEck全球农产品ETF",
    "XLI": "工业行业精选指数ETF-SPDR",
    "ITA": "iShares美国航空航天与国防ETF",
    "PKB": "Invesco动力住宅建设ETF",
    "PAVE": "Global X美国基础设施发展ETF",
    "IYT": "iShares交通运输ETF",
    "JETS": "U.S. Global Jets航空业ETF",
    "BOAT": "SonicShares全球航运ETF",
    "IFRA": "iShares美国基础设施ETF",
    "UFO": "Procure太空ETF",
    "SHLD": "Strive美国国防与航空航天ETF",
    "XLE": "能源行业精选指数ETF-SPDR",
    "IEZ": "iShares美国石油设备与服务ETF",
    "XOP": "SPDR标普石油天然气开采ETF",
    "FAN": "First Trust全球风能ETF",
    "TAN": "Invesco太阳能ETF",
    "NLR": "VanEck铀及核能ETF",
    "XLB": "原材料行业精选指数ETF-SPDR",
    "XME": "SPDR标普金属与采矿ETF",
    "WOOD": "iShares全球林业ETF",
    "COPX": "Global X铜矿股ETF",
    "GLD": "SPDR黄金ETF",
    "GLTR": "Aberdeen标准实物贵金属篮子ETF",
    "SLV": "iShares白银ETF",
    "SLX": "VanEck矢量钢铁ETF",
    "BATT": "Amplify锂电池及关键材料ETF",
    "XLC": "通信服务行业精选指数ETF-SPDR",
    "IYZ": "iShares美国电信ETF",
    "PNQI": "Invesco纳斯达克互联网ETF",
    "XLRE": "房地产行业精选指数ETF-SPDR",
    "INDS": "Pacer工业地产ETF",
    "REZ": "iShares住宅与多户家庭地产投资信托ETF",
    "SRVR": "Pacer数据基础设施与房地产ETF",
    "XLU": "公用事业行业精选指数ETF-SPDR",
    "ICLN": "iShares全球清洁能源ETF",
    "PHO": "Invesco水资源ETF",
    "GRID": "First Trust纳斯达克智能电网基础设施ETF",
    "QQQ": "Invesco纳斯达克100指数ETF",
    "SPY": "SPDR标普500指数ETF",
    "TLT": "iShares 20年期以上美国国债ETF",
    "EEM": "iShares MSCI新兴市场ETF",
    "VEA": "Vanguard FTSE发达市场ETF",
    "FXI": "iShares中国大盘股ETF",
    "ARKK": "ARK创新ETF",
    "BITO": "ProShares比特币策略ETF",
    "MSOS": "AdvisorShares纯大麻ETF",
    "IPO": "Renaissance IPO ETF",
    "GBTC": "灰度比特币现货ETF",
    "ETHE": "灰度以太坊现货ETF",
}

# ETF 按板块分类
ETF_LIBRARY: Dict[str, List[str]] = {
    "01 信息技术": ["XLK", "SOXX", "AIQ", "SKYY", "QTUM", "BUG", "IGV"],
    "02 医疗保健": ["XLV", "XHE", "IHF", "XBI", "PJP"],
    "03 金融": ["XLF", "KBE", "IYG", "KIE", "BLOK", "KCE", "REM"],
    "04 可选消费": ["XLY", "CARZ", "XRT", "XHB", "PEJ"],
    "05 必需消费": ["XLP", "PBJ", "MOO"],
    "06 工业": ["XLI", "ITA", "PKB", "PAVE", "IYT", "JETS", "BOAT", "IFRA", "UFO", "SHLD"],
    "07 能源": ["XLE", "IEZ", "XOP", "FAN", "TAN", "NLR"],
    "08 原材料": ["XLB", "PKB", "XME", "WOOD", "COPX", "GLD", "GLTR", "SLV", "SLX", "BATT"],
    "09 通信服务": ["XLC", "IYZ", "PNQI"],
    "10 房地产": ["XLRE", "INDS", "REZ", "SRVR"],
    "11 公用事业": ["XLU", "ICLN", "PHO", "GRID"],
    "12 全球宏观/另类": ["TLT", "EEM", "VEA", "FXI", "ARKK", "BITO", "MSOS", "IPO", "UFO", "GBTC", "ETHE"],
}

# 兼容旧接口的 ETF 列表
TRACKED_ETFS: List[dict] = [
    {"symbol": sym, "name": CHINESE_NAMES.get(sym, sym), "category": sector}
    for sector, symbols in ETF_LIBRARY.items()
    for sym in symbols
]

# FMP API 配置
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

# 时间周期映射（天数）
TIMESERIES_MAP = {
    "1w": 7,
    "1mo": 31,
    "3mo": 92,
    "1y": 365,
}

# K 线数据抓取的日历天数
CANDLE_CALENDAR_DAYS = {
    "day": 365,    # 1 年日 K，约 252 根
    "week": 730,   # 2 年周 K，约 104 根
    "month": 1825, # 5 年月 K，约 60 根
}

# Pandas 重采样规则
RESAMPLE_RULE = {
    "week": "W-FRI",
    "month": "ME",   # pandas ≥2.2 month-end
}
