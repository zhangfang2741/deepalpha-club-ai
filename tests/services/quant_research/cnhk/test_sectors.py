"""行业映射覆盖：2026-09-30 实测的全部东财行业名都要映射到 GICS 板块。"""

from app.services.quant_research.cnhk.sectors import (
    CN_INDUSTRY_TO_GICS,
    HK_INDUSTRY_TO_GICS,
    HK_OVERRIDES,
    cn_sector,
    hk_sector,
)
from app.services.quant_research.universe import GICS_SECTORS

# A 股全市场（RPT_VALUEANALYSIS_DET.BOARD_NAME，2026-09-30）
CN_OBSERVED = (
    "汽车零部件 通用设备 专用设备 半导体 化学制品 化学制药 电网设备 医疗器械 IT服务Ⅱ 软件开发 电力 环境治理 电池 消费电子 "
    "光学光电子 自动化设备 通信设备 计算机设备 房地产开发 塑料 家居用品 光伏设备 元件 中药Ⅱ 农化制品 化学原料 军工电子Ⅱ "
    "服装家纺 生物制品 工业金属 一般零售 医疗服务 航空装备Ⅱ 证券Ⅱ 物流 包装印刷 工程咨询服务Ⅱ 基础建设 银行Ⅱ 专业工程 "
    "通信服务 装修建材 电子化学品Ⅱ 金属新材料 其他电源设备Ⅱ 工程机械 航运港口 家电零部件Ⅱ 其他电子Ⅱ 专业服务 铁路公路 "
    "纺织制造 风电设备 轨交设备Ⅱ 燃气Ⅱ 医药商业 炼化及贸易 广告营销 出版 化学纤维 食品加工 饮料乳品 电机Ⅱ 小金属 多元金融 "
    "农产品加工 环保设备Ⅱ 煤炭开采 旅游及景区 造纸 游戏Ⅱ 休闲食品 水泥 橡胶 小家电 普钢 养殖业 文娱用品 种植业 装修装饰Ⅱ "
    "综合Ⅱ 白酒Ⅱ 摩托车及其他 影视院线 互联网电商 饲料 教育 非白酒 非金属材料Ⅱ 化妆品 调味发酵品Ⅱ 房地产服务 数字媒体 饰品 "
    "玻璃玻纤 照明设备Ⅱ 油服工程 贸易Ⅱ 个护用品 电视广播Ⅱ 贵金属 航空机场 商用车 动物保健Ⅱ 地面兵装Ⅱ 能源金属 特钢Ⅱ 白色家电 "
    "航海装备Ⅱ 冶钢原料 航天装备Ⅱ 黑色家电 厨卫电器 酒店餐饮 汽车服务 房屋建设Ⅱ 乘用车 专业连锁Ⅱ 焦炭Ⅱ 渔业 油气开采Ⅱ "
    "医疗美容 保险Ⅱ 林业Ⅱ 农业综合Ⅱ 体育Ⅱ 其他家电Ⅱ 旅游零售Ⅱ"
).split()

# 港股通标的（RPT_HKF10_INFO_ORGPROFILE.BELONG_INDUSTRY，2026-10-03）
HK_OBSERVED = (
    "药品及生物科技 工业工程 软件服务 地产 食物饮品 资讯科技器材 其他医疗保健 公用事业 工用运输 其他金融 半导体 "
    "旅游及消闲设施 银行 汽车 一般金属及矿石 媒体及娱乐 家庭电器及用品 保险 建筑 纺织及服饰 原材料 石油及天然气 专业零售 "
    "电讯 黄金及贵金属 综合企业 煤炭 消费者主要零售商 农业产品 支援服务 工用支援"
).split()


def test_all_observed_cn_industries_mapped():
    assert len(CN_OBSERVED) == 128
    assert [n for n in CN_OBSERVED if cn_sector(n) is None] == []


def test_all_observed_hk_industries_mapped():
    assert [n for n in HK_OBSERVED if hk_sector("00001", n) is None] == []


def test_mapping_targets_are_gics_keys():
    for v in [*CN_INDUSTRY_TO_GICS.values(), *HK_INDUSTRY_TO_GICS.values(), *HK_OVERRIDES.values()]:
        assert v in GICS_SECTORS


def test_hk_override_wins():
    assert hk_sector("00700", "软件服务") == "communication_services"
    assert hk_sector("00020", "软件服务") == "information_technology"
    assert cn_sector("白酒Ⅱ") == "consumer_staples"
    assert cn_sector("不存在的行业") is None
