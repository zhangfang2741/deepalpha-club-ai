"""东财行业 → GICS 一级行业（与美股同一套 11 个板块键，见 universe.GICS_SECTORS）。

A 股行业名接近申万二级（128 个，2026-09-30 全市场实测）；港股为东财港股行业（约 31 个）。
映射按 GICS 定义逐个人工判定：电池 / 光伏逆变器类按电气设备归工业，光伏硅片组件、元件、光学光电子归信息技术，
互联网电商、教育归可选消费，游戏、广告、出版、影视归通信服务，焦炭归能源（煤炭与消费用燃料）。
港股「软件服务」里混着互联网平台，按 GICS 实际归属覆盖少数大型公司（HK_OVERRIDES）。
未映射的行业返回 None（该股不进样本，记日志），新行业出现时补在这里。
"""

from __future__ import annotations

_COMM, _DISC, _STAP, _ENGY = "communication_services", "consumer_discretionary", "consumer_staples", "energy"
_FIN, _HC, _IND, _IT = "financials", "health_care", "industrials", "information_technology"
_MAT, _RE, _UTIL = "materials", "real_estate", "utilities"

CN_INDUSTRY_TO_GICS: dict[str, str] = {
    # 信息技术
    "半导体": _IT, "IT服务Ⅱ": _IT, "软件开发": _IT, "消费电子": _IT, "光学光电子": _IT, "通信设备": _IT,
    "计算机设备": _IT, "元件": _IT, "其他电子Ⅱ": _IT, "光伏设备": _IT,
    # 工业
    "通用设备": _IND, "专用设备": _IND, "电网设备": _IND, "环境治理": _IND, "电池": _IND, "自动化设备": _IND,
    "军工电子Ⅱ": _IND, "航空装备Ⅱ": _IND, "物流": _IND, "工程咨询服务Ⅱ": _IND, "基础建设": _IND,
    "专业工程": _IND, "其他电源设备Ⅱ": _IND, "工程机械": _IND, "航运港口": _IND, "专业服务": _IND,
    "铁路公路": _IND, "风电设备": _IND, "轨交设备Ⅱ": _IND, "电机Ⅱ": _IND, "环保设备Ⅱ": _IND,
    "装修装饰Ⅱ": _IND, "综合Ⅱ": _IND, "照明设备Ⅱ": _IND, "贸易Ⅱ": _IND, "航空机场": _IND, "商用车": _IND,
    "地面兵装Ⅱ": _IND, "航海装备Ⅱ": _IND, "航天装备Ⅱ": _IND, "房屋建设Ⅱ": _IND,
    # 原材料
    "化学制品": _MAT, "塑料": _MAT, "农化制品": _MAT, "化学原料": _MAT, "工业金属": _MAT, "包装印刷": _MAT,
    "装修建材": _MAT, "电子化学品Ⅱ": _MAT, "金属新材料": _MAT, "化学纤维": _MAT, "小金属": _MAT, "造纸": _MAT,
    "水泥": _MAT, "橡胶": _MAT, "普钢": _MAT, "非金属材料Ⅱ": _MAT, "玻璃玻纤": _MAT, "贵金属": _MAT,
    "能源金属": _MAT, "特钢Ⅱ": _MAT, "冶钢原料": _MAT, "林业Ⅱ": _MAT,
    # 医疗保健
    "化学制药": _HC, "医疗器械": _HC, "中药Ⅱ": _HC, "生物制品": _HC, "医疗服务": _HC, "医药商业": _HC,
    "动物保健Ⅱ": _HC, "医疗美容": _HC,
    # 可选消费
    "汽车零部件": _DISC, "家居用品": _DISC, "服装家纺": _DISC, "一般零售": _DISC, "家电零部件Ⅱ": _DISC,
    "纺织制造": _DISC, "旅游及景区": _DISC, "小家电": _DISC, "文娱用品": _DISC, "摩托车及其他": _DISC,
    "互联网电商": _DISC, "教育": _DISC, "饰品": _DISC, "白色家电": _DISC, "黑色家电": _DISC, "厨卫电器": _DISC,
    "酒店餐饮": _DISC, "汽车服务": _DISC, "乘用车": _DISC, "专业连锁Ⅱ": _DISC, "体育Ⅱ": _DISC,
    "其他家电Ⅱ": _DISC, "旅游零售Ⅱ": _DISC,
    # 必需消费
    "食品加工": _STAP, "饮料乳品": _STAP, "农产品加工": _STAP, "休闲食品": _STAP, "养殖业": _STAP,
    "种植业": _STAP, "白酒Ⅱ": _STAP, "饲料": _STAP, "非白酒": _STAP, "化妆品": _STAP, "调味发酵品Ⅱ": _STAP,
    "个护用品": _STAP, "渔业": _STAP, "农业综合Ⅱ": _STAP,
    # 通信服务
    "通信服务": _COMM, "广告营销": _COMM, "出版": _COMM, "游戏Ⅱ": _COMM, "影视院线": _COMM,
    "数字媒体": _COMM, "电视广播Ⅱ": _COMM,
    # 能源
    "炼化及贸易": _ENGY, "煤炭开采": _ENGY, "油服工程": _ENGY, "焦炭Ⅱ": _ENGY, "油气开采Ⅱ": _ENGY,
    # 金融
    "证券Ⅱ": _FIN, "银行Ⅱ": _FIN, "多元金融": _FIN, "保险Ⅱ": _FIN,
    # 房地产 / 公用事业
    "房地产开发": _RE, "房地产服务": _RE,
    "电力": _UTIL, "燃气Ⅱ": _UTIL,
}

HK_INDUSTRY_TO_GICS: dict[str, str] = {
    "药品及生物科技": _HC, "其他医疗保健": _HC,
    "工业工程": _IND, "工用运输": _IND, "建筑": _IND, "综合企业": _IND, "支援服务": _IND, "工用支援": _IND,
    "软件服务": _IT, "资讯科技器材": _IT, "半导体": _IT,
    "地产": _RE,
    "食物饮品": _STAP, "消费者主要零售商": _STAP, "农业产品": _STAP,
    "公用事业": _UTIL,
    "其他金融": _FIN, "银行": _FIN, "保险": _FIN,
    "旅游及消闲设施": _DISC, "汽车": _DISC, "家庭电器及用品": _DISC, "纺织及服饰": _DISC, "专业零售": _DISC,
    "一般金属及矿石": _MAT, "原材料": _MAT, "黄金及贵金属": _MAT,
    "媒体及娱乐": _COMM, "电讯": _COMM,
    "石油及天然气": _ENGY, "煤炭": _ENGY,
}

# 港股「软件服务」等行业里按 GICS 实际归属不同的大型公司（代码为 5 位）
HK_OVERRIDES: dict[str, str] = {
    "00700": _COMM,   # 腾讯控股
    "09988": _DISC,   # 阿里巴巴
    "03690": _DISC,   # 美团
    "09618": _DISC,   # 京东集团
    "09961": _DISC,   # 携程集团
    "01024": _COMM,   # 快手
    "09888": _COMM,   # 百度集团
    "09999": _COMM,   # 网易
    "09626": _COMM,   # 哔哩哔哩
    "09898": _COMM,   # 微博
    "00772": _COMM,   # 阅文集团
    "02423": _RE,     # 贝壳
    "06618": _STAP,   # 京东健康
}


def cn_sector(industry: str | None) -> str | None:
    """A 股东财行业 → GICS 板块键。"""
    return CN_INDUSTRY_TO_GICS.get((industry or "").strip())


def hk_sector(code: str, industry: str | None) -> str | None:
    """港股（5 位代码）→ GICS 板块键：先看覆盖表，再按行业映射。"""
    return HK_OVERRIDES.get(code) or HK_INDUSTRY_TO_GICS.get((industry or "").strip())
