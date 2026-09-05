# 后端八字排盘引擎设计

**日期**：2026-09-05
**范围**：`app/services/bazi/` 无状态计算服务 + AI 解读（子项目，来自 [2026-09-05-deepalpha-bazi-app-design.md](2026-09-05-deepalpha-bazi-app-design.md) 中"底层引擎"部分）
**不包含**：紫微斗数排盘、订阅权限校验、iOS 客户端实现、家人命盘管理

## 1. 架构

新增无状态计算服务 `app/services/bazi/`：
- **不落库**——用户填写的生辰信息和排盘结果不持久化到后端数据库；iOS 客户端如需保存由本地 SwiftData 负责（属于 iOS 子项目范围）
- **不做鉴权/订阅权限校验**——付费墙判断先由 iOS 客户端根据本地订阅状态决定调用哪个接口，服务端强校验留给未来的订阅子项目
- 遵循项目分层规则：`app/api/v1/bazi.py` 只做请求解析/参数校验/调用 service，业务逻辑在 `app/services/bazi/`

**核心依赖**：`lunar-python`（`uv add lunar-python`）。该库已验证支持所需的全部计算：
- 阳历⇄农历转换
- 四柱排盘（年/月/日/时柱的天干地支）
- 五行、十神、纳音
- 大运（`eightchar.Yun` / `eightchar.DaYun`）、流年（`eightchar.LiuNian`）

不自己实现干支历法的天文计算（节气、闰月等边界情况极易出错）。

## 2. 数据模型（Pydantic，不落库）

`app/schemas/bazi.py`：

```python
class BaziChartRequest(BaseModel):
    birth_date: date              # 阳历出生日期
    birth_time: time | None       # None 表示时辰不确定
    birth_city: str               # 用于真太阳时校正，如"北京"
    gender: Literal["male", "female"]  # 决定大运顺逆排

class Pillar(BaseModel):
    gan: str
    zhi: str
    na_yin: str
    shi_shen_gan: str
    shi_shen_zhi: str

class DaYunStep(BaseModel):
    gan_zhi: str
    start_age: int
    end_age: int

class BaziChartResponse(BaseModel):
    hour_known: bool
    solar_date: date
    lunar_date: str
    true_solar_time: datetime | None       # 校正后时间；hour_known=False 时为 None
    true_solar_time_applied: bool          # 城市表是否命中
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    time_pillar: Pillar | None             # hour_known=False 时为 None
    wu_xing_distribution: dict[str, int]   # {"jin": 2, "mu": 1, "shui": 3, "huo": 1, "tu": 1}
    da_yun: list[DaYunStep]
    liu_nian_gan_zhi: str                  # 当前年份的流年干支

class InterpretationRequest(BaseModel):
    birth_date: date
    birth_time: time | None
    birth_city: str
    gender: Literal["male", "female"]
    section: Literal["daily", "deep"]

class InterpretationResponse(BaseModel):
    text: str
```

## 3. 模块划分

```
app/services/bazi/
├── __init__.py
├── chart.py                      # 封装 lunar-python，组装 BaziChartResponse
├── true_solar_time.py            # 经度时差校正逻辑
├── data/
│   └── cn_city_longitude.json    # 内置中国城市经度静态表（省会+主要地级市）
└── interpretation.py             # 调 llm_service 生成 daily/deep 两种文案

app/core/prompts/bazi/
├── daily.md                       # 今日运势一句话 prompt 模板
└── deep.md                        # 深度解读长文 prompt 模板

app/api/v1/bazi.py                 # POST /chart 、POST /interpretation

tests/services/bazi/
├── test_chart.py
├── test_true_solar_time.py
└── test_interpretation.py

tests/api/v1/
└── test_bazi.py
```

`app/api/v1/api.py` 新增一行注册：
```python
api_router.include_router(bazi_router, prefix="/bazi", tags=["bazi"])
```

Prompt 加载沿用 `app/core/prompts/__init__.py` 的现有约定（模块加载时一次性读文件到常量，避免每次请求做文件 I/O）。

## 4. API

### `POST /api/v1/bazi/chart`

输入生辰信息，返回完整结构化排盘数据。始终返回全部字段（不做付费墙拦截，计算成本低，没必要拦）。

### `POST /api/v1/bazi/interpretation`

输入生辰信息 + `section`，调用 `llm_service.call()` 生成对应的 AI 解读文本：
- `section="daily"`：免费。短文本，基于当日流日干支和用户八字的关系生成"今日一句话运势 + 宜忌"。
- `section="deep"`：付费点。长文本，综合解读大运流年 + 性格 + 事业 + 财运 + 婚姻，一篇文章覆盖，不拆成 4 个独立接口（降低复杂度，符合 YAGNI）。

`section=deep` 是否可调用，由 iOS 客户端根据本地订阅状态决定，本服务不做拦截。

## 5. 关键设计点

### 5.1 真太阳时校正

用户选择"做真太阳时校正"（而非直接用输入的钟表时间排盘）。经度数据来源：**内置中国城市经度静态表**（`app/services/bazi/data/cn_city_longitude.json`），覆盖省会及主要地级市，用户从下拉框选择城市（iOS 端），离线可用，无需调用第三方地理编码 API。

- 城市名命中静态表 → 按经度与东八区中心线（东经120°）的时差校正出生时间，再用校正后的时间排盘，`true_solar_time_applied=True`
- 命中不到（海外城市、生僻地名、iOS 端未来若支持自由文本输入）→ 降级为不校正，直接用输入的钟表时间排盘，`true_solar_time_applied=False`，不报错、不阻断流程

### 5.2 时辰未知

`birth_time=None` 时：
- 只排年/月/日三柱，`time_pillar=None`
- 五行分布、十神统计不包含时柱部分
- 大运计算不受影响——大运顺逆排法由年干阴阳 + 性别决定，从月柱起排，不依赖时柱

### 5.3 AI 解读分档

只做 `daily` / `deep` 两档，不按性格/事业/财运/婚姻拆成 4 个独立 LLM 调用接口。理由：减少 API 数量和 prompt 维护成本，`deep` 一次生成的长文本身可以在文章内部分段覆盖多个主题，iOS 端渲染成带小标题的长文即可，不需要后端拆分接口。

### 5.4 付费墙边界（有意不做的事）

本服务不做任何订阅/权限校验。`/chart` 和 `/interpretation` 对所有调用方一视同仁。真正的服务端强制校验（如根据 App Store 订阅收据判断用户是否有权调用 `section=deep`）留给未来的订阅子项目，避免在订阅体系还没设计好之前引入一套临时的、后续要推倒重来的权限方案。

## 6. 测试策略

- **`test_chart.py`**：使用 2-3 组已知的标准八字案例（生日+时辰 → 预期四柱干支，来自公开可验证的排盘工具输出）做精确断言，覆盖"时辰已知"和"时辰未知"两条路径，验证五行统计和大运表的正确性
- **`test_true_solar_time.py`**：覆盖"城市命中静态表"和"城市命中不到"两个分支，断言校正后的时间差符合经度计算公式
- **`test_interpretation.py`**：mock `app.services.llm.llm_service.call`，验证 `daily`/`deep` 两种 section 拼装的 prompt 内容和调用参数，不做真实 LLM 调用
- **`test_bazi.py`**：FastAPI `TestClient` 测试两个端点的请求校验（如 `birth_date` 格式错误 → 422，`gender` 非法枚举 → 422）

## 7. 依赖变更

- `pyproject.toml` 新增依赖：`lunar-python`（`uv add lunar-python`）
- 无数据库迁移（不落库）
- 无新增环境变量

## 8. 验收标准

- [ ] `POST /api/v1/bazi/chart` 输入一组已知生辰，返回的四柱干支、五行分布、大运表与公开排盘工具的结果一致
- [ ] `birth_time=None` 时正确降级为三柱，`time_pillar` 为 `null`，大运表仍正常输出
- [ ] `birth_city` 命中内置经度表时应用真太阳时校正，命中不到时降级不报错
- [ ] `POST /api/v1/bazi/interpretation` 的 `daily`/`deep` 两种 section 都能正确调用 `llm_service` 并返回文本
- [ ] 所有单元测试通过，`make check`（ruff + pyright）无报错
