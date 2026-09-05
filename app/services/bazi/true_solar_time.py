"""真太阳时校正：按出生地经度对钟表时间做时差修正。

只做经度时差校正（每偏离东八区中心线1度校正4分钟），不做全年逐日的
均时差(equation of time)修正——这是命理类应用常见的简化做法。
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

_DATA_PATH = Path(__file__).parent / "data" / "cn_city_longitude.json"
with open(_DATA_PATH, "r", encoding="utf-8") as _f:
    _CITY_LONGITUDE: Dict[str, float] = json.load(_f)

_REFERENCE_LONGITUDE = 120.0  # 东八区(UTC+8)中心经线


def correct_birth_datetime(dt: datetime, city: str) -> Tuple[datetime, bool]:
    """按出生地经度校正钟表时间为真太阳时。

    Args:
        dt: 用户输入的钟表时间（阳历）。
        city: 出生城市名，需与内置经度表的键完全匹配。

    Returns:
        (校正后的时间, 是否命中经度表并完成校正)。命中不到时原样返回 dt。
    """
    longitude = _CITY_LONGITUDE.get(city.strip())
    if longitude is None:
        return dt, False
    offset_minutes = round((longitude - _REFERENCE_LONGITUDE) * 4)
    return dt + timedelta(minutes=offset_minutes), True
