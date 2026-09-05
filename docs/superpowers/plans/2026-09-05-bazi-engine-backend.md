# 后端八字排盘引擎 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个无状态的后端服务 `app/services/bazi/`，提供两个 REST API（排盘 `/api/v1/bazi/chart`、AI 解读 `/api/v1/bazi/interpretation`），供未来的 iOS App 消费。

**Architecture:** 用开源库 `lunar-python` 做干支历法/四柱/五行/十神/大运计算（不自己实现天文算法）；出生地经度做真太阳时校正（内置中国城市经度静态表，命中不到则降级不校正）；AI 解读复用现有 `llm_service.call()`，只做 `daily`（免费一句话）/`deep`（付费长文）两档。整个服务不落库、不做订阅权限校验。

**Tech Stack:** Python 3.13 / FastAPI / Pydantic v2 / `lunar-python` / 现有 `app.services.llm.llm_service`

---

## 前置说明（写给执行这个计划的工程师）

- 本仓库测试用 pytest，`asyncio_mode=auto`（`pyproject.toml`），async 测试函数不需要写 `@pytest.mark.asyncio`。
- Mock `llm_service.call` 的仓库惯例是 `monkeypatch.setattr(module.llm_service, "call", fake_call)`，`fake_call` 是一个普通的 `async def` 函数，不是 `unittest.mock.AsyncMock`（参考 `tests/test_transcript_ai.py`）。
- Pydantic schema 惯例：**请求体**模型继承 `pydantic.BaseModel`；**响应体**模型继承 `app.schemas.base.BaseResponse`（自动带 `request_id` 字段）；字段用 `typing.Optional[X]` 而不是 `X | None`，都带 `Field(description=...)`。
- `app/api/v1/*.py` 路由文件只做参数校验/调用 service；业务逻辑一律放 `app/services/bazi/`。
- 本计划里所有排盘相关的"预期值"（四柱干支、五行统计、大运表等）都是**直接运行 `lunar-python` 库实测得到的真实输出**，不是编造的，可以放心作为断言目标。
- 全局提交时机：每个 Task 完成后单独 `git commit`，不要攒到最后一起提交。
- **与设计 spec 的一处修正**：[2026-09-05-bazi-engine-backend-design.md](2026-09-05-bazi-engine-backend-design.md) 里 `Pillar.shi_shen_zhi` 写的类型是 `str`，实测 `lunar-python` 的 `getYearShiShenZhi()` 等方法返回的是 `list[str]`（地支藏干可能对应多个十神，如"未"藏干对应 `["正印", "正官", "正财"]`），本计划按实际类型改为 `List[str]`。

---

## Task 1: 安装 `lunar-python` 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 安装依赖**

Run: `uv add lunar-python`

Expected: `pyproject.toml` 的 `dependencies` 里新增一行 `"lunar-python>=1.4.8"`，`uv.lock` 同步更新。

- [ ] **Step 2: 验证可以正常 import**

Run:
```bash
uv run python -c "from lunar_python import Solar; print(Solar.fromYmdHms(1990,5,15,14,30,0).getLunar().getEightChar().getYearGan())"
```

Expected: 输出 `庚`（不报错）

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(bazi): 引入lunar-python依赖用于干支历法计算"
```

---

## Task 2: 真太阳时校正模块

**Files:**
- Create: `app/services/bazi/__init__.py`
- Create: `app/services/bazi/data/cn_city_longitude.json`
- Create: `app/services/bazi/true_solar_time.py`
- Test: `tests/services/bazi/__init__.py`
- Test: `tests/services/bazi/test_true_solar_time.py`

- [ ] **Step 1: 创建空的包初始化文件**

`app/services/bazi/__init__.py`:
```python
"""八字排盘无状态计算服务：干支历法排盘 + AI 解读。"""
```

`tests/services/bazi/__init__.py`:
```python
```

- [ ] **Step 2: 创建内置城市经度静态表**

`app/services/bazi/data/cn_city_longitude.json`:
```json
{
  "北京": 116.4074,
  "上海": 121.4737,
  "广州": 113.2644,
  "深圳": 114.0579,
  "成都": 104.0668,
  "杭州": 120.1551,
  "南京": 118.7969,
  "武汉": 114.3055,
  "西安": 108.9402,
  "重庆": 106.5516,
  "天津": 117.2010,
  "苏州": 120.5853,
  "长沙": 112.9388,
  "郑州": 113.6254,
  "青岛": 120.3826,
  "大连": 121.6147,
  "厦门": 118.0894,
  "昆明": 102.8329,
  "哈尔滨": 126.5349,
  "沈阳": 123.4315,
  "济南": 117.0009,
  "合肥": 117.2272,
  "福州": 119.2965,
  "南昌": 115.8582,
  "太原": 112.5489,
  "石家庄": 114.5149,
  "兰州": 103.8236,
  "贵阳": 106.6302,
  "南宁": 108.3665,
  "海口": 110.1999,
  "乌鲁木齐": 87.6168,
  "拉萨": 91.1409,
  "呼和浩特": 111.7519,
  "银川": 106.2309,
  "西宁": 101.7782,
  "香港": 114.1694,
  "澳门": 113.5491,
  "台北": 121.5654
}
```

- [ ] **Step 3: 写失败的测试**

`tests/services/bazi/test_true_solar_time.py`:
```python
"""真太阳时校正测试。"""

from datetime import datetime

from app.services.bazi.true_solar_time import correct_birth_datetime


def test_correct_birth_datetime_known_city_applies_offset():
    """北京经度116.4074，比东八区中心线120°偏西，应校正为更早的时间。"""
    dt = datetime(1990, 5, 15, 14, 30, 0)
    corrected, applied = correct_birth_datetime(dt, "北京")
    assert applied is True
    assert corrected == datetime(1990, 5, 15, 14, 16, 0)


def test_correct_birth_datetime_unknown_city_returns_original():
    """命中不到城市表时，原样返回输入时间，且标记为未校正。"""
    dt = datetime(1990, 5, 15, 14, 30, 0)
    corrected, applied = correct_birth_datetime(dt, "东京")
    assert applied is False
    assert corrected == dt
```

- [ ] **Step 4: 运行测试确认失败**

Run: `uv run pytest tests/services/bazi/test_true_solar_time.py -v`
Expected: `FAIL` / `ModuleNotFoundError: No module named 'app.services.bazi.true_solar_time'`

- [ ] **Step 5: 实现真太阳时校正模块**

`app/services/bazi/true_solar_time.py`:
```python
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
    longitude = _CITY_LONGITUDE.get(city)
    if longitude is None:
        return dt, False
    offset_minutes = round((longitude - _REFERENCE_LONGITUDE) * 4)
    return dt + timedelta(minutes=offset_minutes), True
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/services/bazi/test_true_solar_time.py -v`
Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add app/services/bazi/__init__.py app/services/bazi/data/cn_city_longitude.json app/services/bazi/true_solar_time.py tests/services/bazi/__init__.py tests/services/bazi/test_true_solar_time.py
git commit -m "feat(bazi): 新增真太阳时校正模块，内置中国城市经度表"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `app/schemas/bazi.py`

- [ ] **Step 1: 直接编写 schema（纯数据模型，不需要先写失败测试；正确性由 Task 4/6 的集成测试覆盖）**

`app/schemas/bazi.py`:
```python
"""八字排盘与 AI 解读的请求/响应 schema。"""

from datetime import date, datetime, time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.base import BaseResponse


class BaziChartRequest(BaseModel):
    birth_date: date = Field(description="阳历出生日期")
    birth_time: Optional[time] = Field(None, description="出生时间，None 表示时辰不确定")
    birth_city: str = Field(description="出生城市，用于真太阳时校正")
    gender: Literal["male", "female"] = Field(description="性别，决定大运顺逆排")


class Pillar(BaseModel):
    gan: str = Field(description="天干")
    zhi: str = Field(description="地支")
    na_yin: str = Field(description="纳音")
    shi_shen_gan: str = Field(description="天干十神")
    shi_shen_zhi: List[str] = Field(description="地支藏干对应的十神列表")


class DaYunStep(BaseModel):
    gan_zhi: str = Field(description="大运干支")
    start_age: int = Field(description="起始虚岁")
    end_age: int = Field(description="结束虚岁")


class BaziChartResponse(BaseResponse):
    hour_known: bool = Field(description="出生时辰是否已知")
    solar_date: date = Field(description="阳历出生日期")
    lunar_date: str = Field(description="农历日期描述")
    true_solar_time: Optional[datetime] = Field(None, description="真太阳时校正后的时间，时辰未知时为 None")
    true_solar_time_applied: bool = Field(description="是否命中内置经度表并完成校正")
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    time_pillar: Optional[Pillar] = Field(None, description="时柱，时辰未知时为 None")
    wu_xing_distribution: Dict[str, int] = Field(description="五行分布计数，键为 jin/mu/shui/huo/tu")
    da_yun: List[DaYunStep] = Field(description="大运表，共8步(80年)")
    liu_nian_gan_zhi: str = Field(description="当前年份的流年干支")


class InterpretationRequest(BaseModel):
    birth_date: date = Field(description="阳历出生日期")
    birth_time: Optional[time] = Field(None, description="出生时间，None 表示时辰不确定")
    birth_city: str = Field(description="出生城市，用于真太阳时校正")
    gender: Literal["male", "female"] = Field(description="性别，决定大运顺逆排")
    section: Literal["daily", "deep"] = Field(description="daily=今日运势(免费) / deep=深度解读(付费)")


class InterpretationResponse(BaseResponse):
    text: str = Field(description="AI 生成的解读文本")
```

- [ ] **Step 2: 快速手动验证可以正常构造（不算单元测试，只是 sanity check）**

Run:
```bash
uv run python -c "
from app.schemas.bazi import BaziChartRequest
r = BaziChartRequest(birth_date='1990-05-15', birth_time='14:30:00', birth_city='北京', gender='male')
print(r)
"
```
Expected: 打印出 `BaziChartRequest(...)`，不报错

- [ ] **Step 3: Commit**

```bash
git add app/schemas/bazi.py
git commit -m "feat(bazi): 新增八字排盘与AI解读的Pydantic schema"
```

---

## Task 4: 八字排盘核心逻辑

**Files:**
- Create: `app/services/bazi/chart.py`
- Test: `tests/services/bazi/test_chart.py`

- [ ] **Step 1: 写失败的测试（时辰已知 + 真太阳时校正）**

`tests/services/bazi/test_chart.py`:
```python
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
    assert result.true_solar_time.hour == 14
    assert result.true_solar_time.minute == 30
    # 14:30 和校正后的14:16都落在未时(13-15点)区间内，四柱不受影响
    assert result.year_pillar.gan == "庚"
    assert result.time_pillar.gan == "癸"
    assert result.time_pillar.zhi == "未"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/services/bazi/test_chart.py -v`
Expected: `FAIL` / `ModuleNotFoundError: No module named 'app.services.bazi.chart'`

- [ ] **Step 3: 实现排盘核心逻辑**

`app/services/bazi/chart.py`:
```python
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


def build_bazi_chart(request: BaziChartRequest) -> BaziChartResponse:
    """根据生辰信息计算八字排盘（四柱/五行/十神/大运/流年）。"""
    hour_known = request.birth_time is not None
    naive_dt = datetime.combine(
        request.birth_date, request.birth_time if hour_known else _UNKNOWN_HOUR_PLACEHOLDER
    )

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
        na_yin=ec.getYearNaYin(),
        shi_shen_gan=ec.getYearShiShenGan(),
        shi_shen_zhi=ec.getYearShiShenZhi(),
    )
    month_pillar = Pillar(
        gan=ec.getMonthGan(),
        zhi=ec.getMonthZhi(),
        na_yin=ec.getMonthNaYin(),
        shi_shen_gan=ec.getMonthShiShenGan(),
        shi_shen_zhi=ec.getMonthShiShenZhi(),
    )
    day_pillar = Pillar(
        gan=ec.getDayGan(),
        zhi=ec.getDayZhi(),
        na_yin=ec.getDayNaYin(),
        shi_shen_gan=ec.getDayShiShenGan(),
        shi_shen_zhi=ec.getDayShiShenZhi(),
    )

    wu_xing_sources = [ec.getYearWuXing(), ec.getMonthWuXing(), ec.getDayWuXing()]

    time_pillar: Pillar | None = None
    if hour_known:
        time_pillar = Pillar(
            gan=ec.getTimeGan(),
            zhi=ec.getTimeZhi(),
            na_yin=ec.getTimeNaYin(),
            shi_shen_gan=ec.getTimeShiShenGan(),
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/services/bazi/test_chart.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/bazi/chart.py tests/services/bazi/test_chart.py
git commit -m "feat(bazi): 实现八字排盘核心逻辑(四柱/五行/十神/大运/流年)"
```

---

## Task 5: AI 解读（daily / deep 两档）

**Files:**
- Create: `app/core/prompts/bazi/__init__.py`
- Create: `app/core/prompts/bazi/daily.md`
- Create: `app/core/prompts/bazi/deep.md`
- Create: `app/services/bazi/interpretation.py`
- Test: `tests/services/bazi/test_interpretation.py`

- [ ] **Step 1: 创建 prompt 模板文件**

`app/core/prompts/bazi/daily.md`:
```markdown
你是一位经验丰富的中文命理顾问，专注于八字（四柱）分析。你的任务是根据用户的八字信息，写一句简短的"今日运势"点评。

要求：
- 只写1-2句话，风格温和、正向，避免绝对化的断言（不说"一定会""绝对"）
- 结合用户八字的日主五行与当日流年的关系，给出今日的宜与忌各一条
- 输出格式：先一句话总评，再另起一行写"宜：xxx | 忌：xxx"
- 不要输出任何解释性前后缀，不要提及你是AI
```

`app/core/prompts/bazi/deep.md`:
```markdown
你是一位经验丰富的中文命理顾问，专注于八字（四柱）分析。你的任务是根据用户的完整八字排盘信息，撰写一篇结构化的深度解读长文。

要求：
- 按以下四个小标题分段撰写：性格特质、事业发展、财运走势、婚姻感情
- 每个部分3-5句话，结合用户的日主五行、十神配置、当前大运展开分析
- 语气专业、克制，避免宿命论式的绝对断言，可以提出建议而非单纯预测
- 全文使用中文，用 Markdown 二级标题（##）分隔四个部分
- 不要输出任何解释性前后缀，不要提及你是AI
```

`app/core/prompts/bazi/__init__.py`:
```python
"""八字 AI 解读的 prompt 模板：daily(今日运势) / deep(深度解读)。"""

import os

_PROMPTS_DIR = os.path.dirname(__file__)

with open(os.path.join(_PROMPTS_DIR, "daily.md"), "r") as _f:
    DAILY_PROMPT = _f.read()

with open(os.path.join(_PROMPTS_DIR, "deep.md"), "r") as _f:
    DEEP_PROMPT = _f.read()
```

- [ ] **Step 2: 写失败的测试**

`tests/services/bazi/test_interpretation.py`:
```python
"""AI 解读（daily/deep）测试，mock llm_service.call。"""

from datetime import date, time

from app.core.prompts.bazi import DAILY_PROMPT, DEEP_PROMPT
from app.schemas.bazi import InterpretationRequest
from app.services.bazi import interpretation as interpretation_module
from app.services.bazi.interpretation import generate_interpretation


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


async def test_generate_interpretation_daily_uses_daily_prompt(monkeypatch):
    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _FakeMessage("今天适合签约 | 宜：签约 忌：争执")

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    request = InterpretationRequest(
        birth_date=date(1990, 5, 15),
        birth_time=time(14, 30, 0),
        birth_city="北京",
        gender="male",
        section="daily",
    )
    result = await generate_interpretation(request)

    assert result.text == "今天适合签约 | 宜：签约 忌：争执"
    system_message, human_message = captured["messages"]
    assert system_message.content == DAILY_PROMPT
    assert "年柱：庚午" in human_message.content
    assert "性别：男" in human_message.content


async def test_generate_interpretation_deep_uses_deep_prompt(monkeypatch):
    captured = {}

    async def fake_call(messages, **kwargs):
        captured["messages"] = messages
        return _FakeMessage("## 性格特质\n...")

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    request = InterpretationRequest(
        birth_date=date(1990, 5, 15),
        birth_time=None,
        birth_city="北京",
        gender="female",
        section="deep",
    )
    result = await generate_interpretation(request)

    assert result.text == "## 性格特质\n..."
    system_message, human_message = captured["messages"]
    assert system_message.content == DEEP_PROMPT
    assert "时柱：未知（出生时辰不确定）" in human_message.content
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/services/bazi/test_interpretation.py -v`
Expected: `FAIL` / `ModuleNotFoundError: No module named 'app.services.bazi.interpretation'`

- [ ] **Step 4: 实现 interpretation.py**

`app/services/bazi/interpretation.py`:
```python
"""八字 AI 解读：daily(免费今日运势) / deep(付费深度解读) 两档文案生成。"""

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.prompts.bazi import DAILY_PROMPT, DEEP_PROMPT
from app.schemas.bazi import (
    BaziChartRequest,
    BaziChartResponse,
    InterpretationRequest,
    InterpretationResponse,
    Pillar,
)
from app.services.bazi.chart import build_bazi_chart
from app.services.llm import llm_service

_GENDER_LABEL = {"male": "男", "female": "女"}
_SECTION_PROMPT = {"daily": DAILY_PROMPT, "deep": DEEP_PROMPT}


def _describe_pillar(name: str, pillar: Optional[Pillar]) -> str:
    if pillar is None:
        return f"{name}：未知（出生时辰不确定）"
    shi_shen_zhi = "、".join(pillar.shi_shen_zhi)
    return f"{name}：{pillar.gan}{pillar.zhi}（纳音：{pillar.na_yin}，十神：{pillar.shi_shen_gan}/{shi_shen_zhi}）"


def _describe_chart(chart: BaziChartResponse, gender: Literal["male", "female"]) -> str:
    wu_xing_line = "、".join(f"{k}{v}" for k, v in chart.wu_xing_distribution.items())
    da_yun_line = "、".join(f"{d.gan_zhi}({d.start_age}-{d.end_age}岁)" for d in chart.da_yun)
    return "\n".join(
        [
            f"性别：{_GENDER_LABEL[gender]}",
            f"阳历生日：{chart.solar_date}",
            f"农历：{chart.lunar_date}",
            _describe_pillar("年柱", chart.year_pillar),
            _describe_pillar("月柱", chart.month_pillar),
            _describe_pillar("日柱", chart.day_pillar),
            _describe_pillar("时柱", chart.time_pillar),
            f"五行分布：{wu_xing_line}",
            f"大运：{da_yun_line}",
            f"今年流年：{chart.liu_nian_gan_zhi}",
        ]
    )


async def generate_interpretation(request: InterpretationRequest) -> InterpretationResponse:
    """调用 AI 生成今日运势(daily)或深度解读(deep)文案。"""
    chart = build_bazi_chart(
        BaziChartRequest(
            birth_date=request.birth_date,
            birth_time=request.birth_time,
            birth_city=request.birth_city,
            gender=request.gender,
        )
    )
    chart_description = _describe_chart(chart, request.gender)
    result = await llm_service.call(
        [
            SystemMessage(content=_SECTION_PROMPT[request.section]),
            HumanMessage(content=chart_description),
        ]
    )
    return InterpretationResponse(text=result.content)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/services/bazi/test_interpretation.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add app/core/prompts/bazi/ app/services/bazi/interpretation.py tests/services/bazi/test_interpretation.py
git commit -m "feat(bazi): 新增AI解读daily/deep两档文案生成"
```

---

## Task 6: API 路由

**Files:**
- Create: `app/api/v1/bazi.py`
- Modify: `app/api/v1/api.py`
- Test: `tests/api/test_bazi.py`

现有 API 端点测试都放在 `tests/api/`（扁平结构，没有按 `v1` 再分子目录，如 `tests/api/test_chan_auth.py`），本任务沿用这个惯例，不新建 `tests/api/v1/` 目录。`tests/api/conftest.py` 里的 `_disable_rate_limiter` 是 autouse fixture，会自动对这个新文件生效，不需要额外处理。

- [ ] **Step 1: 写失败的测试**

`tests/api/test_bazi.py`:
```python
"""八字 API 端点测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.bazi import interpretation as interpretation_module

client = TestClient(app)


def test_get_bazi_chart_success():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_time": "14:30:00",
            "birth_city": "北京",
            "gender": "male",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hour_known"] is True
    assert body["year_pillar"]["gan"] == "庚"
    assert body["year_pillar"]["zhi"] == "午"
    assert body["true_solar_time_applied"] is True


def test_get_bazi_chart_hour_unknown():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "female",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hour_known"] is False
    assert body["time_pillar"] is None


def test_get_bazi_chart_invalid_gender_returns_422():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "unknown",
        },
    )
    assert response.status_code == 422


def test_get_bazi_chart_invalid_date_returns_422():
    response = client.post(
        "/api/v1/bazi/chart",
        json={
            "birth_date": "not-a-date",
            "birth_city": "北京",
            "gender": "male",
        },
    )
    assert response.status_code == 422


def test_get_bazi_interpretation_success(monkeypatch):
    class _FakeMessage:
        content = "今天适合签约 | 宜：签约 忌：争执"

    async def fake_call(messages, **kwargs):
        return _FakeMessage()

    monkeypatch.setattr(interpretation_module.llm_service, "call", fake_call)

    response = client.post(
        "/api/v1/bazi/interpretation",
        json={
            "birth_date": "1990-05-15",
            "birth_time": "14:30:00",
            "birth_city": "北京",
            "gender": "male",
            "section": "daily",
        },
    )
    assert response.status_code == 200
    assert response.json()["text"] == "今天适合签约 | 宜：签约 忌：争执"


def test_get_bazi_interpretation_invalid_section_returns_422():
    response = client.post(
        "/api/v1/bazi/interpretation",
        json={
            "birth_date": "1990-05-15",
            "birth_city": "北京",
            "gender": "male",
            "section": "not-a-section",
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/api/test_bazi.py -v`
Expected: `FAIL` / 404（路由还没注册）

- [ ] **Step 3: 实现路由文件**

`app/api/v1/bazi.py`:
```python
"""八字排盘与 AI 解读 API 端点。"""

from fastapi import APIRouter

from app.schemas.bazi import (
    BaziChartRequest,
    BaziChartResponse,
    InterpretationRequest,
    InterpretationResponse,
)
from app.services.bazi.chart import build_bazi_chart
from app.services.bazi.interpretation import generate_interpretation

router = APIRouter()


@router.post("/chart", response_model=BaziChartResponse)
async def get_bazi_chart(request: BaziChartRequest) -> BaziChartResponse:
    """根据生辰信息计算八字排盘（四柱/五行/十神/大运/流年）。"""
    return build_bazi_chart(request)


@router.post("/interpretation", response_model=InterpretationResponse)
async def get_bazi_interpretation(request: InterpretationRequest) -> InterpretationResponse:
    """调用 AI 生成今日运势(daily)或深度解读(deep)文案。"""
    return await generate_interpretation(request)
```

- [ ] **Step 4: 注册路由**

Modify `app/api/v1/api.py`：现有 import 区是按字母序排列的（`analysis` → `analyst_upgrade` → `auth` → `chan` → ...），在 `from app.api.v1.auth import router as auth_router` 这一行之后、`from app.api.v1.chan import router as chan_router` 之前插入：
```python
from app.api.v1.bazi import router as bazi_router
```

同样地，在 `api_router.include_router(auth_router, prefix="/auth", tags=["auth"])` 之后、`api_router.include_router(chan_router, prefix="/chan", tags=["chan"])` 之前插入：
```python
api_router.include_router(bazi_router, prefix="/bazi", tags=["bazi"])
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/api/test_bazi.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/bazi.py app/api/v1/api.py tests/api/test_bazi.py
git commit -m "feat(bazi): 新增/api/v1/bazi路由(chart+interpretation)"
```

---

## Task 7: 全量检查

**Files:** 无新文件，仅验证

- [ ] **Step 1: 跑全量相关测试**

Run: `uv run pytest tests/services/bazi/ tests/api/test_bazi.py -v`
Expected: 全部 `passed`（Task 2/4/5/6 的测试总计 13 个用例）

- [ ] **Step 2: 跑 lint + 类型检查**

Run: `make check`
Expected: `ruff check .` 和 `pyright` 都无报错（`pyright` 配置是 `typeCheckingMode = "standard"`，对无类型标注的第三方库默认不会报 `reportMissingTypeStubs` 错误）。如果实际运行后 pyright 在 `app/services/bazi/chart.py` 里对 `lunar_python` 的调用报错，在具体报错的那一行末尾加 `# pyright: ignore[规则名]`（如 `# pyright: ignore[reportUnknownMemberType]`），不要整个文件禁用类型检查。

- [ ] **Step 3: 跑全量测试套件，确认没有破坏其他模块**

Run: `uv run pytest -m "not slow"`
Expected: 全部 `passed`

- [ ] **Step 4: Commit（如果 Step 2 产生了修改）**

```bash
git add -A
git commit -m "chore(bazi): 修复lint/类型检查问题"
```

---

## 验收标准回顾

- [x] `POST /api/v1/bazi/chart` 输入已知生辰，返回的四柱干支、五行分布、大运表与 `lunar-python` 库直接计算的结果一致（Task 4 测试覆盖）
- [x] `birth_time=None` 时正确降级为三柱，`time_pillar` 为 `null`，大运表仍正常输出（Task 4 测试覆盖）
- [x] `birth_city` 命中内置经度表时应用真太阳时校正，命中不到时降级不报错（Task 2、Task 4 测试覆盖）
- [x] `POST /api/v1/bazi/interpretation` 的 `daily`/`deep` 两种 section 都能正确调用 `llm_service` 并返回文本（Task 5、Task 6 测试覆盖）
- [x] 所有单元测试通过，`make check`（ruff + pyright）无报错（Task 7）
