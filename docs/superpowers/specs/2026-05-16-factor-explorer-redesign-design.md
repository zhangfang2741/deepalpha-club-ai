# 因子探索（Skill Generator）重设计

> 日期：2026-05-16
> 状态：草稿
> 作者：Claude（基于与 @zhangfang 的 brainstorming）

---

## 一、背景

当前 `/skill-generator`（前端称"因子探索"）已上线但存在三类问题：

1. **价值闭环缺失**：「发布到 Skill 市场」是假按钮（仅前端 `setPublished(true)`），无任何持久化；做完一个因子后用户什么都"剩不下"。
2. **交互流程不顺**：
   - 顶部"股票选择条"被父布局负边距（`-mx-6 -my-8`）+ `bg-gray-950 h-full` 拉高，遮挡 TopNav；移动端 input 容易被挤掉，出现"导航没了 / 没地方选股"现象。
   - 整页深色 `bg-gray-950`，与全站浅色（`oklch(0.985)` 背景 + 蓝色 primary）视觉割裂。
   - "起步必须先输股票代码" + 单股票聊天框形态，定位是"工具"而非"剧场"。
   - 模板 6 个固定按钮全是技术指标（动量/均线/波动/趋势/RSI/成交量），缺少业务化包装。
3. **工程及 LLM 隐患**：
   - 沙箱 `_SAFE_BUILTINS` 含 `getattr/setattr`，配合 `__class__.__base__.__subclasses__()` 在标准 CPython 下存在子类逃逸面。
   - K 线缓存 key 不含 `user_id`（`skill_kline:{symbol}:{start}:{end}:{freq}`），跨用户共享。
   - 错误处理散在 `loadError` / `runError` / 流响应 catch 三处，体验不一致。
   - Prompt 强迫"不能说 Python/代码/函数"，反而让 AI 难调试，token 浪费在每次完整重写代码。

## 二、目标与范围

### 2.1 目标用户

**DeepAlpha 已登录用户**（付费 / 注册用户，不面向匿名访客）。本功能是**内部产品的"功能营销"**——让用户感受 AI + 量化的"哇一下"，并通过累积「我的因子」资产留下来用更深的功能。

### 2.2 体验目标

| 维度 | 目标 |
| --- | --- |
| 第一眼 | 进入页面默认看「案例馆」Hero + 副网格，立刻"哇" |
| 探索 | 任一案例点入 → 深色 K 线 + AI 旁白 → 想换股票/想自己出题 |
| 沉淀 | 用一键「保存到我的因子」累积资产；下次进入"我的因子"tab 能回看 |
| 二次玩 | 每个因子定义都能"换股重跑"，跑完结果不会覆盖默认快照 |

### 2.3 不在范围

明确**不做**：

- 多股票 / 截面验证 / IC / 收益率 / 分组回测等严肃量化指标
- 基本面因子（income / balance / cashflow 接入 —— 现有空 DataFrame 接口先保留为占位）
- "公开案例库" 让用户提名 / 投票（`is_public` 字段先留空，未来扩展）
- 移动端深度优化（响应式不破即可，复杂图表移动端默认提示"请用桌面端"）
- 因子之间组合 / 多因子打分

## 三、用户故事与流程

```text
┌─ 案例馆 ──────────────────────┐
│  Hero（今日精选）             │
│  └→ 4 张副卡片                │
│        │                       │
│        ▼ 点入                  │
└─→  详情页 ──────────────────→  保存到我的因子
        │ 换股重跑              │
        ▼                       ▼
     新快照（缓存）           ┌─ 我的因子 ──────────────────┐
                              │  我保存的卡片墙             │
                              │  └→ 点入相同的详情页        │
                              └─────────────────────────────┘

         「新建」tab：三步向导（选股 → 选命题/自由描述 → AI 生成 + 旁白）
                                 │
                                 ▼ 跑完
                              详情页（同款）→ 保存
```

## 四、页面与视觉

### 4.1 路由与 Tab

复用现有路由 `/skill-generator`（不改 URL），内部用 `?tab=` query string 切换三个视图（避免 Next.js App Router 子路由配置成本）。

| Tab | query | 内容 |
| --- | --- | --- |
| 案例馆（默认） | `?tab=gallery` 或无参数 | Hero + 副网格 |
| 我的因子 | `?tab=mine` | 用户保存的卡片墙（同款卡片） |
| 新建 | `?tab=new` | 三步向导 + 故事化双图 |

详情页用 `?factor_id=<id>` 触发模态/全屏（用 `useSearchParams` 控制），不离开 SPA、可分享深链接。

### 4.1.1 「新建」tab 三步向导

| 步骤 | 内容 | 状态机 |
| --- | --- | --- |
| ① 选股 | sticky 工具栏：股票代码 input + 起止日期 + 粒度 + 「加载数据」按钮 | 加载成功 → 步骤 2 解锁 |
| ② 选命题 / 自由描述 | 6 类业务化命题 chip（强者恒强 / 跌深必反 / 波动突破 / 量价共振 / 情绪极端 / 技术指标）+ 多行 textarea 兜底自由输入 | 提交后 → 步骤 3 流式启动 |
| ③ AI 生成 + 旁白 | 左侧实时输出代码思路 + 右侧双图渲染因子 + 底部 CTA「保存到我的因子」/「丢弃重来」 | 保存后跳转到该 skill 的详情页 |

UX 关键：步骤 2 自由输入与命题 chip 互斥不强制，可以"选了 chip 再补一句"。步骤 3 失败可回退到步骤 2 重试，不重置股票。

### 4.1.2 Hero 主推轮换规则

第一版用**手动 pin**：`factor_skills` 加 `pin_priority: int | None` 字段，`NULL` 表示不 pin。展示规则：

1. `pin_priority IS NOT NULL` 的精选案例按 `pin_priority ASC` 排序，取第一个作 Hero。
2. 其余 owner_id IS NULL 的案例按 `pin_priority`（无值的排后）+ `created_at DESC` 作副网格。

第一批 seed 时手动给 NVDA 案例设 `pin_priority=1`。运营换 Hero 只需 UPDATE 一行 SQL。

### 4.2 视觉系统

**与全站对齐**：浅色背景 (`bg-background` ≈ `oklch(0.985)`)、蓝色 primary (`oklch(0.585 0.233 257.23)`)、白色卡片 + `border-gray-200` + 圆角 `rounded-xl` (`--radius:0.75rem`)。

**特例**：详情页的 K 线/因子双图卡片用 **深色** `#0b1220`，作为"焦点反差" —— 给金融数据一个"专业操盘台"小舞台。这是页面唯一深色区域，其余（指标卡、AI 旁白、面包屑）保持浅色。

**关键视觉元素**（在 mockup 中已经过用户确认，存档于 `.superpowers/brainstorm/`）：

- 顶部面包屑：极简文字，标题 + `⭐ 精选` 蓝色徽章
- 4 张指标卡：每张左侧 3px 彩色 accent 竖条（蓝/橙/绿/紫）
- K 线主图：深色卡片 + 白色大字股价 + 涨绿色 chip + 时间段切换
- 信号点：橙色脉冲圆环 + `①②③④` 编号 + 悬停放大
- 因子副图：`BaselineSeries`（蓝色正向、红色反向）+ ±1σ 虚线参考线
- AI 旁白卡片：渐变方块头像 `α` + "DeepAlpha AI · 资深量化研究员视角" + `⚡ 已缓存 0.2s` chip
- 三段旁白：每段一根彩色 accent 竖线（蓝 ① 立意 / 橙 ② 关键时点 / 绿 ③ 适用失效）
- 主 CTA「保存到我的因子」：蓝色渐变 + 双层阴影

### 4.3 修复当前 UI bug

1. **去掉负边距强占父容器**：删除 `frontend/app/(dashboard)/skill-generator/page.tsx:373` 的 `-mx-6 -my-8`，改为 Tab 内部容器使用 dashboard layout 提供的标准 padding。
2. **TopNav 不被遮**：内容由 dashboard layout 的 `<main>` 容器承载，自然不会覆盖 nav。
3. **股票选择器**：「新建」tab 内部强制可见，包在 sticky 工具条里；「案例馆 / 我的因子」根本不需要选股票（每个卡片自带）。
4. **整页深色**改为**浅色**为底，仅详情页双图卡片局部深色。

## 五、数据模型

### 5.1 新表 `factor_skills`

继承 `app.db.base.UUIDModel`（UUID 主键 + `created_at` + `updated_at`）：

```python
# app/models/factor_skill.py
class FactorSkill(UUIDModel, table=True):
    __tablename__ = "factor_skills"

    owner_id: int | None         # NULL = 平台精选案例；非 NULL 关联 users.id
    title: str                   # "英伟达·AI 行情动量"
    description: str             # 一句话商业描述
    category: str                # 'momentum' | 'reversal' | 'volatility' | 'volume' | 'sentiment' | 'technical' | 'custom'
    code: str                    # 沙箱可执行的 Python 代码（已通过 AST 检查）
    default_symbol: str          # 默认股票
    default_start_date: str      # YYYY-MM-DD
    default_end_date: str        # YYYY-MM-DD
    default_freq: str            # 'daily' | 'weekly'
    snapshot_factor_jsonb: dict  # 默认快照：{ "factor": [{time, value}], "signals": [...], "metrics": {...} }
    narrative_jsonb: dict | None # AI 旁白：{ "thesis": str, "key_points": [{date, z, text}], "verdict": {applicable, fails} }
    is_public: bool = False      # 预留：未来支持用户提名公开

    __table_args__ = (
        Index("ix_factor_skills_owner", "owner_id"),
        Index("ix_factor_skills_category", "category"),
    )
```

**关键设计**：

- `snapshot_factor_jsonb` 不存 K 线（K 线可按 symbol 重新拉取），只存因子曲线 + 信号点 + 指标卡数据。打开详情页时 K 线走 `kline` 端点（用户级缓存），因子直接渲染快照。
- `narrative_jsonb` 在首次保存时生成并写入，"换股重跑"会另写到独立的 `factor_runs` 表（详见 5.2），不污染原快照。
- `category` 用枚举字符串而非 enum 类型，便于运营加新类型。

### 5.2 新表 `factor_runs`（重跑历史，可选）

存"换股重跑"产生的结果，用于秒回查看 + 节省重复计算：

```python
class FactorRun(UUIDModel, table=True):
    __tablename__ = "factor_runs"

    skill_id: UUID               # FK -> factor_skills.id
    user_id: int                 # 谁跑的
    symbol: str
    start_date: str
    end_date: str
    freq: str
    factor_jsonb: dict           # 同 snapshot_factor_jsonb 结构
    narrative_jsonb: dict | None # 该次的 AI 旁白（可能与默认快照不同）

    __table_args__ = (
        UniqueConstraint("skill_id", "user_id", "symbol", "start_date", "end_date", "freq", name="uq_factor_run"),
    )
```

**TTL 策略**：通过 Alembic 加定期清理任务（或留作 v2 优化）：保留每个用户每个 skill 最近 10 次跑，更早的删除。

### 5.3 Alembic 迁移

```bash
uv run alembic revision --autogenerate -m "add factor_skills and factor_runs tables"
```

随后单独写一个 **case seed 迁移**（非 autogenerate）：

```bash
uv run alembic revision -m "seed factor explorer gallery cases"
```

种子内容：6~9 个手工策划的精选案例（owner_id=NULL）。第一批建议：

1. 英伟达 · AI 行情动量（NVDA）
2. 贵州茅台 · 均值回归（600519）
3. 沪深 300 · 恐慌指数信号（沪深 300 ETF）
4. 特斯拉 · 波动率突破（TSLA）
5. 中国平安 · RSI 极值（601318）
6. 宁德时代 · 量价背离（300750）

每个种子记录都需附带 `snapshot_factor_jsonb` —— **种子运行时不调 LLM**，因子计算用 hardcoded 代码（与 seed 文件同捆），但需要拉一次真实 K 线再做计算，所以 seed 脚本接受 `--with-data` 参数：

```bash
uv run python scripts/seed_factor_cases.py --with-data
```

会写入完整快照。生产环境（Railway）部署时跑一次即可。

## 六、API 设计

新增/重命名后的路由（基于现有 `app/api/v1/skills.py`）：

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/skills/gallery` | 案例馆列表（owner_id IS NULL） |
| `GET` | `/api/v1/skills/mine` | 我的因子列表（owner_id = current_user.id） |
| `GET` | `/api/v1/skills/{id}` | 单个 skill 详情（含 snapshot + narrative） |
| `POST` | `/api/v1/skills/generate` | 保留 —— SSE 流式生成代码（用于新建 tab） |
| `POST` | `/api/v1/skills/run` | 保留 —— 沙箱执行 |
| `POST` | `/api/v1/skills/save` | 把当前会话的 code + symbol + range 保存为新 skill |
| `POST` | `/api/v1/skills/{id}/rerun` | 换股重跑，写入 `factor_runs`（带缓存） |
| `POST` | `/api/v1/skills/{id}/narrative` | （可选 v2）重新生成旁白 |
| `DELETE` | `/api/v1/skills/{id}` | 删除我的因子（owner check） |
| `GET` | `/api/v1/skills/kline` | 保留 —— K 线（cache key 加 user_id 前缀） |

**旧的 `POST /api/v1/skills/run`** 不再被新建之外的流程调用，但保留兼容。

### 6.1 Schemas（`app/schemas/skills.py`）

新增（节选）：

```python
class FactorSkillBrief(BaseModel):
    id: UUID
    title: str
    description: str
    category: str
    default_symbol: str
    is_public: bool
    created_at: datetime

class FactorSkillDetail(FactorSkillBrief):
    code: str
    default_start_date: str
    default_end_date: str
    default_freq: str
    snapshot: dict  # snapshot_factor_jsonb
    narrative: dict | None

class SaveSkillRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=200)
    category: str
    code: str = Field(..., max_length=20000)
    symbol: str
    start_date: str
    end_date: str
    freq: Literal["daily", "weekly"] = "daily"

class RerunRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    freq: Literal["daily", "weekly"] = "daily"
```

## 七、沙箱重写（subprocess + RLIMIT）

### 7.1 方案

把 `_run_in_sandbox` 从同线程 `exec()` 迁出到独立 Python 子进程：

```python
# app/services/skills/sandbox.py
async def run_in_subprocess(
    code: str,
    price_records: list[dict],
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    timeout: float = 30.0,
) -> tuple[list[dict], str]:
    """以独立 Python 子进程执行 skill，setrlimit 限 CPU/内存/fd。"""
    payload = json.dumps({"code": code, "price": price_records, "symbol": symbol,
                          "start_date": start_date, "end_date": end_date})

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.services.skills.sandbox_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=_apply_rlimits,  # 仅 Linux 有效
        env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"},  # 隐去敏感 env
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=payload.encode()), timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise ValueError("Skill 执行超时（30秒）")

    if proc.returncode != 0:
        raise ValueError(f"Skill 执行失败：{stderr.decode()[:500]}")

    result = json.loads(stdout)
    return result["records"], result["output_type"]


def _apply_rlimits():
    import resource
    # CPU 30s、虚拟内存 512MB、文件大小 10MB、最多 32 fd、不允许 fork
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
```

### 7.2 sandbox_worker.py

一个独立模块，从 stdin 读 JSON，执行后从 stdout 写 JSON。**仍保留**现有 AST 检查 + 受限 builtins 作为**第二道防线**（防御深度，不依赖单一隔离层）。

### 7.3 平台兼容

- **Linux（Railway、Docker）**：完整 RLIMIT 生效。
- **macOS / Windows 本地开发**：`preexec_fn` 兼容性差，降级到只跑超时 + 不设 RLIMIT，但开发者明确知道这是"非安全模式"，CI 上跑测试时验证 Linux 行为。

## 八、AI 旁白系统

### 8.1 生成时机

- 首次保存（`POST /skills/save`）：流式生成 narrative，落库 `narrative_jsonb`。
- 「换股重跑」：在 `factor_runs.narrative_jsonb` 上独立生成（每个组合的旁白都不同）。
- 详情页打开：直接渲染缓存的 `narrative_jsonb`，**不再调 LLM**。

### 8.2 数据结构

```jsonc
{
  "thesis": "「动量加速」假设强者恒强 —— 取过去 60 个交易日的累计涨幅...",
  "key_points": [
    {"date": "2024-04-08", "z": 3.14, "text": "AI 主升浪初期，H100 订单井喷..."},
    {"date": "2025-04-28", "z": -2.17, "text": "关税恐慌叠加 DeepSeek 冲击..."}
  ],
  "verdict": {
    "applicable": "主题行情主升浪 · 宽基大盘 · 趋势顺畅龙头股",
    "fails": "震荡市 · 估值剧变 · 个股有重大利空时的尾部风险"
  },
  "generated_at": "2026-05-16T14:30:00Z",
  "model": "claude-sonnet-4-6"
}
```

### 8.3 Prompt 重做

新的 system prompt（`app/services/skills/narrator.py`）：

- **改掉**"绝对不提 Python/代码/函数" —— 这条让调试痛苦。新规则：在**代码生成**阶段允许说技术词；在**旁白生成**阶段强制业务化语言。两个 prompt 分开。
- 旁白生成时，把"已计算出的因子曲线 + 信号点 + 股票基本信息"作为 context 喂给 LLM，让它讲故事，**不再让 LLM 推断数学**。
- LLM 调用走 `llm_service.call()`，自动 fallback。

### 8.4 信号点选取

不依赖 LLM，规则化（确定性 + 不消耗 token）：

1. 因子值 z-score 标准化。
2. 找 `|z| ≥ 1.5` 的所有"穿越事件"（连续在阈值外的局部极值）。
3. 按 `|z|` 排序，取 top 4。
4. 把这 4 个时点 + 当时股价 + 因子值喂给 LLM 让它叙事。

## 九、工程加固

### 9.1 K 线缓存隔离

```python
# 修改 _kline_cache_key
def _kline_cache_key(user_id: int | None, symbol: str, start: str, end: str, freq: str) -> str:
    prefix = f"u{user_id}" if user_id else "public"
    return f"skill_kline:{prefix}:{symbol}:{start}:{end}:{freq}"
```

`public` 前缀给案例馆共用（owner_id IS NULL 的 skill 走 public 缓存）。

### 9.2 错误处理统一

新增 `app/services/skills/errors.py`：

```python
class SkillError(Exception): pass
class SkillSyntaxError(SkillError): pass
class SkillSandboxError(SkillError): pass
class SkillDataError(SkillError): pass
class SkillTimeoutError(SkillError): pass
```

API 层统一捕获 → 返回结构化 JSON：

```json
{"error": {"code": "SANDBOX_TIMEOUT", "message": "因子计算超时（>30s），请简化逻辑"}}
```

前端 toast 显示 message，控制台保留 code。

### 9.3 services 拆包

把现有 `app/services/skills.py`（单文件 431 行）拆成包：

```text
app/services/skills/
├── __init__.py
├── generator.py      # 代码流式生成
├── runner.py         # 沙箱执行编排
├── sandbox.py        # subprocess 沙箱
├── sandbox_worker.py # 子进程入口
├── narrator.py       # AI 旁白生成
├── kline.py          # K 线 fetch + 缓存
├── errors.py
└── ast_check.py      # AST 安全检查（保留）
```

### 9.4 频率限制收紧

`slowapi` 现状基于 IP，登录页登录后所有用户共用一个出口 IP 时会互相挤占。**调整为 user-based**：通过 `key_func=lambda req: f"u{req.state.user_id}"` 在认证中间件后注入。

| 端点 | 现状 | 调整后（按用户） |
| --- | --- | --- |
| `/generate` | 20/分 | 10/分（流式，单次成本高） |
| `/kline` | 30/分 | 60/分（缓存命中率高，宽松） |
| `/run` | 10/分 | 10/分（保留） |
| `/save` | 无 | 20/分 |
| `/rerun` | 无 | 30/分 |

## 十、前端实现要点

### 10.1 文件结构

```text
frontend/
├── app/(dashboard)/skill-generator/
│   ├── page.tsx                    # Tab 调度 + 路由
│   ├── _components/
│   │   ├── GalleryView.tsx         # 案例馆 Hero + 网格
│   │   ├── MineView.tsx            # 我的因子卡片墙
│   │   ├── NewView.tsx             # 三步向导
│   │   ├── DetailPage.tsx          # 详情页（模态/全屏）
│   │   ├── FactorCard.tsx          # 通用卡片组件
│   │   ├── MetricCards.tsx         # 4 张指标卡
│   │   ├── DualChart.tsx           # K 线 + 因子双图（深色）
│   │   └── NarrativePanel.tsx      # AI 旁白卡片
│   └── _hooks/
│       ├── useSkillStream.ts       # 流式生成
│       └── useFactorData.ts        # 详情页数据加载
├── lib/api/skills.ts                # 已存在，扩展端点
└── lib/store/skills.ts              # 新增 Zustand：当前选中的 skill_id、迷你 detail 缓存
```

### 10.2 K 线图升级

复用 `lightweight-charts@5.0.7`（项目已装）。详情页 `DualChart` 用 `BaselineSeries` 实现因子副图（蓝色渐变正向 / 红色渐变反向 + 0 轴）+ `createSeriesMarkers` 高亮信号点（参考 `.superpowers/brainstorm/.../detail-page-real.html` 已验证可行）。

### 10.3 删除/迁移

- 删除 `setPublished` 状态及"发布到 Skill 市场"按钮
- 删除当前 `page.tsx` 的 `-mx-6 -my-8 bg-gray-950 h-full` 包装
- 当前 6 个固定模板移到「新建」tab 的步骤 2 选项里，扩到 6 大类（动量/反转/波动/成交量/情绪/技术指标）

## 十一、测试策略

### 11.1 后端

- `tests/services/skills/test_sandbox.py`：subprocess 沙箱（**Linux only**，CI matrix 用 ubuntu runner）
  - 超时杀进程
  - RLIMIT_AS 限内存（构造大数组）
  - 危险 import（os/subprocess/socket）被 AST 拦截
  - `__class__.__base__.__subclasses__()` 在子进程内即使逃出 AST 检查也无法访问宿主文件系统（验证 fd RLIMIT 生效）
- `tests/services/skills/test_narrator.py`：mock LLM，验证 narrative JSON schema
- `tests/api/test_skills_crud.py`：save / list / detail / delete 端到端，验证 owner 隔离
- `tests/services/skills/test_kline_cache.py`：user_id 缓存隔离

### 11.2 前端

- `frontend/__tests__/skill-generator/`：组件 snapshot + 关键交互（保存按钮、换股输入）
- 端到端：手测三个 tab 切换、详情页打开、保存到我的因子、换股重跑

## 十二、不在范围 / 未来扩展

### 12.1 v1 不做

- 多股票截面验证、IC 计算、分组回测、收益率指标
- 基本面因子（income/balance/cashflow 三个接口保留空实现）
- 用户提名 `is_public` 公开案例（字段保留）
- 移动端深度优化
- 因子组合 / 多因子打分

### 12.2 后续可加

- v1.5：用户能为「我的因子」生成 OG 图片分享链接（带 share_token）
- v2：admin 后台批量管理精选案例 + AI 辅助生成新案例
- v2：单因子多股票截面图（同一因子在 ETF 成分股上的分布）
- v3：因子组合 + 简单回测

## 十三、关键文件清单（实施前 checklist）

**后端新增**：

- `app/models/factor_skill.py`、`app/models/factor_run.py`
- `app/services/skills/`（拆包后）
- `alembic/versions/xxxx_factor_skills.py`、`alembic/versions/xxxx_seed_cases.py`
- `scripts/seed_factor_cases.py`
- `tests/services/skills/*`、`tests/api/test_skills_crud.py`

**后端修改**：

- `app/api/v1/skills.py`（新端点）
- `app/schemas/skills.py`(新 schemas）

**前端新增**：

- `frontend/app/(dashboard)/skill-generator/_components/*`（8 个组件）
- `frontend/app/(dashboard)/skill-generator/_hooks/*`

**前端重写**：

- `frontend/app/(dashboard)/skill-generator/page.tsx`（去掉负边距 + 深色背景，改为 Tab 调度）
- `frontend/lib/api/skills.ts`（扩展端点）

**新增 store**：

- `frontend/lib/store/skills.ts`
