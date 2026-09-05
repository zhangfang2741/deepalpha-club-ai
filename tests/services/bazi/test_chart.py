"""八字排盘核心逻辑测试。

期望值来自直接运行 lunar-python 库的真实输出，不是手算或编造的。
"""

from datetime import date, time

from lunar_python import Solar

from app.schemas.bazi import BaziChartRequest
from app.services.bazi.chart import build_bazi_chart


def test_build_bazi_chart_hour_known_applies_true_solar_time():
    """男性，1990-05-15 14:30 生于北京：应用真太阳时校正后排盘。"""
    request = BaziChartRequest(
        birth_date=date(1990, 5, 15),
        birth_time=time(14, 30, 0),
        birth_city="北京",
        gender="male",
    )

    result = build_bazi_chart(request)

    assert result.hour_known is True
    assert result.true_solar_time_applied is True
    assert result.true_solar_time is not None
    assert result.true_solar_time.hour == 14
    assert result.true_solar_time.minute == 16

    assert result.year_pillar.gan == "庚"
    assert result.year_pillar.zhi == "午"
    assert result.year_pillar.na_yin == "路旁土"
    assert result.year_pillar.shi_shen_gan == "比肩"
    assert result.year_pillar.shi_shen_zhi == ["正官", "正印"]

    assert result.month_pillar.gan == "辛"
    assert result.month_pillar.zhi == "巳"
    assert result.month_pillar.shi_shen_gan == "劫财"

    assert result.day_pillar.gan == "庚"
    assert result.day_pillar.zhi == "辰"

    assert result.time_pillar is not None
    assert result.time_pillar.gan == "癸"
    assert result.time_pillar.zhi == "未"
    assert result.time_pillar.shi_shen_gan == "伤官"

    assert result.wu_xing_distribution == {"jin": 3, "mu": 0, "shui": 1, "huo": 2, "tu": 2}

    assert len(result.da_yun) == 8
    assert result.da_yun[0].gan_zhi == "壬午"
    assert result.da_yun[0].start_age == 8
    assert result.da_yun[0].end_age == 17
    assert result.da_yun[-1].gan_zhi == "己丑"
    assert result.da_yun[-1].start_age == 78
    assert result.da_yun[-1].end_age == 87

    expected_liu_nian = Solar.fromYmd(
        date.today().year, date.today().month, date.today().day
    ).getLunar().getYearInGanZhi()
    assert result.liu_nian_gan_zhi == expected_liu_nian


def test_build_bazi_chart_hour_unknown_skips_time_pillar():
    """女性，时辰不确定：只排三柱，五行/十神不含时柱，大运不受影响。"""
    request = BaziChartRequest(
        birth_date=date(1990, 5, 15),
        birth_time=None,
        birth_city="北京",
        gender="female",
    )

    result = build_bazi_chart(request)

    assert result.hour_known is False
    assert result.true_solar_time is None
    assert result.true_solar_time_applied is False
    assert result.time_pillar is None

    assert result.year_pillar.gan == "庚"
    assert result.year_pillar.zhi == "午"
    assert result.day_pillar.gan == "庚"
    assert result.day_pillar.zhi == "辰"

    assert result.wu_xing_distribution == {"jin": 3, "mu": 0, "shui": 0, "huo": 2, "tu": 1}

    assert len(result.da_yun) == 8
    assert result.da_yun[0].gan_zhi == "庚辰"
    assert result.da_yun[0].start_age == 4
    assert result.da_yun[0].end_age == 13
    assert result.da_yun[-1].gan_zhi == "癸酉"
    assert result.da_yun[-1].start_age == 74
    assert result.da_yun[-1].end_age == 83


def test_build_bazi_chart_unknown_city_skips_correction():
    """城市不在内置经度表里：不校正，直接用输入的钟表时间排盘。"""
    request = BaziChartRequest(
        birth_date=date(1990, 5, 15),
        birth_time=time(14, 30, 0),
        birth_city="东京",
        gender="male",
    )

    result = build_bazi_chart(request)

    assert result.true_solar_time_applied is False
    assert result.true_solar_time is not None
    assert result.true_solar_time.hour == 14
    assert result.true_solar_time.minute == 30
    # 14:30 和校正后的14:16都落在未时(13-15点)区间内，四柱不受影响
    assert result.year_pillar.gan == "庚"
    assert result.time_pillar is not None
    assert result.time_pillar.gan == "癸"
    assert result.time_pillar.zhi == "未"
