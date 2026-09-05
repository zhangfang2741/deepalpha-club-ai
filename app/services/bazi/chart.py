"""八字排盘核心逻辑：封装 lunar-python，输出结构化排盘数据。"""

from datetime import date, datetime, time
from typing import Dict, List

from lunar_python import Solar

from app.schemas.bazi import BaziChartRequest, BaziChartResponse, DaYunStep, Pillar
from app.services.bazi.true_solar_time import correct_birth_datetime

_WU_XING_KEY = {"金": "jin", "木": "mu", "水": "shui", "火": "huo", "土": "tu"}
_GENDER_CODE = {"male": 1, "female": 0}
_DA_YUN_STEPS = 8
_UNKNOWN_HOUR_PLACEHOLDER = time(12, 0, 0)  # 时辰未知时用中午占位，避开子时(23点)的日期边界


def _tally_wu_xing(wu_xing_strings: List[str]) -> Dict[str, int]:
    counts = {key: 0 for key in _WU_XING_KEY.values()}
    for wx in wu_xing_strings:
        for ch in wx:
            if ch in _WU_XING_KEY:
                counts[_WU_XING_KEY[ch]] += 1
    return counts


def _non_null(value: str | None) -> str:
    """lunar-python 的部分 getter 被推断为 Optional[str]，但排盘成功后实际必返回字符串。"""
    assert value is not None
    return value


def build_bazi_chart(request: BaziChartRequest) -> BaziChartResponse:
    """根据生辰信息计算八字排盘（四柱/五行/十神/大运/流年）。"""
    hour_known = request.birth_time is not None
    if request.birth_time is not None:
        naive_dt = datetime.combine(request.birth_date, request.birth_time)
    else:
        naive_dt = datetime.combine(request.birth_date, _UNKNOWN_HOUR_PLACEHOLDER)

    true_solar_time: datetime | None = None
    true_solar_time_applied = False
    calc_dt = naive_dt
    if hour_known:
        calc_dt, true_solar_time_applied = correct_birth_datetime(naive_dt, request.birth_city)
        true_solar_time = calc_dt

    solar = Solar.fromYmdHms(
        calc_dt.year, calc_dt.month, calc_dt.day, calc_dt.hour, calc_dt.minute, calc_dt.second
    )
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    year_pillar = Pillar(
        gan=ec.getYearGan(),
        zhi=ec.getYearZhi(),
        na_yin=_non_null(ec.getYearNaYin()),
        shi_shen_gan=_non_null(ec.getYearShiShenGan()),
        shi_shen_zhi=ec.getYearShiShenZhi(),
    )
    month_pillar = Pillar(
        gan=ec.getMonthGan(),
        zhi=ec.getMonthZhi(),
        na_yin=_non_null(ec.getMonthNaYin()),
        shi_shen_gan=_non_null(ec.getMonthShiShenGan()),
        shi_shen_zhi=ec.getMonthShiShenZhi(),
    )
    day_pillar = Pillar(
        gan=ec.getDayGan(),
        zhi=ec.getDayZhi(),
        na_yin=_non_null(ec.getDayNaYin()),
        shi_shen_gan=_non_null(ec.getDayShiShenGan()),
        shi_shen_zhi=ec.getDayShiShenZhi(),
    )

    wu_xing_sources = [ec.getYearWuXing(), ec.getMonthWuXing(), ec.getDayWuXing()]

    time_pillar: Pillar | None = None
    if hour_known:
        time_pillar = Pillar(
            gan=ec.getTimeGan(),
            zhi=ec.getTimeZhi(),
            na_yin=_non_null(ec.getTimeNaYin()),
            shi_shen_gan=_non_null(ec.getTimeShiShenGan()),
            shi_shen_zhi=ec.getTimeShiShenZhi(),
        )
        wu_xing_sources.append(ec.getTimeWuXing())

    yun = ec.getYun(_GENDER_CODE[request.gender])
    da_yun = [
        DaYunStep(gan_zhi=dy.getGanZhi(), start_age=dy.getStartAge(), end_age=dy.getEndAge())
        for dy in yun.getDaYun(_DA_YUN_STEPS + 1)
        if dy.getIndex() >= 1
    ]

    today = date.today()
    liu_nian_gan_zhi = Solar.fromYmd(today.year, today.month, today.day).getLunar().getYearInGanZhi()

    return BaziChartResponse(
        hour_known=hour_known,
        solar_date=request.birth_date,
        lunar_date=str(lunar),
        true_solar_time=true_solar_time,
        true_solar_time_applied=true_solar_time_applied,
        year_pillar=year_pillar,
        month_pillar=month_pillar,
        day_pillar=day_pillar,
        time_pillar=time_pillar,
        wu_xing_distribution=_tally_wu_xing(wu_xing_sources),
        da_yun=da_yun,
        liu_nian_gan_zhi=liu_nian_gan_zhi,
    )
