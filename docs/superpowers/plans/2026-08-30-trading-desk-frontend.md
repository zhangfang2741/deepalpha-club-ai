# 交易台前端 实施计划（计划二 / 共三）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/trading-desk` 落地三栏交易台界面，消费计划一产出的 SSE 事件流，做到 token 级流式渲染、多空辩论可视化、决策逐步组装、暂停/注入交互。

**Architecture:** 单个 client component 页面。事件流由 `lib/api/trading_desk.ts` 的 SSE 读取器产出，经 Zustand store 的纯函数 reducer 折叠成 UI 状态；组件只读 store，不自己算。断线用 `Last-Event-ID` 重连。

**Tech Stack:** Next.js 16 App Router / React 19 / TypeScript / Tailwind / Zustand / lucide-react

**Spec:** `docs/superpowers/specs/2026-08-30-trading-desk-design.md`（视觉方案 A：全平台浅色）
**依赖:** 计划一已落地并部署，`/api/v1/trading-desk/*` 三个端点可用

---

## 关于测试

本仓库前端**没有测试框架**——`frontend/package.json` 的 scripts 只有 `dev` / `build` / `start` / `lint`，没有 vitest/jest。因此本计划**不采用 TDD 循环**，这是现状约束而非选择。

代价与应对：

- 事件 reducer（`applyEvent`）是整个前端唯一有真实逻辑的地方，写成**不依赖 React 的纯函数**，将来引入 vitest 时可直接测，不用重构
- 每个任务的验收是 `npx tsc --noEmit` + `npm run lint` + 明确的人工核对项
- 引入测试框架属于给项目加基础设施，超出本计划范围；建议作为独立任务处理

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `frontend/lib/api/trading_desk.ts` | 事件类型（对齐后端 schema）+ Axios（创建/控制）+ SSE 读取器 |
| `frontend/lib/store/trading_desk.ts` | Zustand store + 纯函数 `applyEvent` reducer |
| `frontend/components/trading_desk/SignalChip.tsx` | 信号 chip（多/空/中性 + 置信度） |
| `frontend/components/trading_desk/PipelinePanel.tsx` | 左栏：流程条 |
| `frontend/components/trading_desk/TurnCard.tsx` | 一张推理卡片（含辩论分色错位、工具 chip、光标） |
| `frontend/components/trading_desk/StreamPanel.tsx` | 中栏：推理流容器 + 空态 |
| `frontend/components/trading_desk/ConsensusMeter.tsx` | 共识条 |
| `frontend/components/trading_desk/VerdictCard.tsx` | 裁决卡 + 审计链 |
| `frontend/components/trading_desk/DecisionPanel.tsx` | 右栏容器 |
| `frontend/components/trading_desk/TradingDeskTopbar.tsx` | 顶栏：标的输入 + 控制按钮 + 状态灯 + 注入条 |
| `frontend/app/trading-desk/page.tsx` | 三栏组装 + SSE 生命周期 |
| `frontend/components/layout/TopNav.tsx` | 注册导航入口 |

### 设计约束（来自 spec §8）

- 浅色：`bg-gray-50` 底 + `bg-white` 卡片 + `border-gray-200`，`rounded-2xl`
- 看多 `text-green-600`/`#16a34a`，看空 `text-red-500`/`#ef4444`，中性 `text-amber-600`/`#d97706`
- 强调色 `blue-600`（系统消息、人工意见、工具 chip、光标）
- 等宽字体只用于数据、标签、信号、工具名
- 尊重 `prefers-reduced-motion`
- 底部常驻免责声明

### 两个刻意的实现选择

**不做假打字机。** 后端已经是真 token 流，前端直接追加即可。原型里的 `typeInto()` 是因为它没有后端才模拟的；再套一层前端节流反而会让真实的 LLM 停顿消失，也引入不必要的状态。光标只画在「当前未 `turn.done` 的最后一张卡片」末尾。

**store 是唯一真源。** 组件不自己算共识、不自己拼 token。所有派生状态在 reducer 里算好，组件只读。这样将来加测试时，覆盖 `applyEvent` 就等于覆盖了绝大部分逻辑。

---

## Task 1: API 层与事件类型

**Files:**
- Create: `frontend/lib/api/trading_desk.ts`

- [ ] **Step 1: 写类型与 API**

创建 `frontend/lib/api/trading_desk.ts`：

```ts
/**
 * 交易台 API：创建运行 / 控制（Axios）+ SSE 事件流（native fetch）。
 *
 * SSE 用 native fetch 而非 apiClient：Axios 读不了 ReadableStream。
 * 这与 lib/api/skills.ts、app/chat/page.tsx 的既有做法一致。
 *
 * 本文件的类型必须与后端 app/schemas/trading_desk.py 保持一致——
 * 那边是协议的单一真源，改动需两侧同步。
 */
import apiClient, { BASE_URL } from '@/lib/api/client'

export type Polarity = 'bull' | 'bear' | 'neutral'
export type StageGroup = 'analyst' | 'system' | 'debate' | 'manager' | 'trader'

export type EventType =
  | 'run.started'
  | 'stage.active'
  | 'stage.done'
  | 'turn.started'
  | 'agent.tool_call'
  | 'agent.token'
  | 'turn.done'
  | 'agent.signal'
  | 'debate.turn'
  | 'human.note'
  | 'consensus.update'
  | 'run.paused'
  | 'run.resumed'
  | 'verdict'
  | 'run.finished'
  | 'error'

export interface EngineCapabilities {
  supports_pause: boolean
  supports_inject: boolean
  supports_resume_after_restart: boolean
}

export interface StageDescriptor {
  id: string
  name: string
  role: string
  group: StageGroup
}

export interface RunStartedData {
  ticker: string
  trade_date: string
  engine: string
  capabilities: EngineCapabilities
  stages: StageDescriptor[]
}

export interface TurnStartedData {
  turn_id: string
  stage_id: string
  name: string
  role: string
  avatar: string
}

export interface DebateTurnData {
  stage_id: string
  debate_id: string
  side: string
  side_label: string
  polarity: Polarity
  round: number
  turn_id: string
}

export interface SignalData {
  stage_id: string
  name: string
  dir: Polarity
  conf: number
  turn_id: string | null
  extracted: boolean
}

export interface ConsensusData {
  bull: number
  neutral: number
  bear: number
  lean: string
}

export interface VerdictData {
  signal: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  size_fraction: number
  entry_reference_price: number | null
  target_price: number | null
  stop_loss: number | null
  currency: string | null
  time_horizon_days: number | null
  rationale: string
  warning_message: string | null
}

export interface RunFinishedData {
  status: 'completed' | 'cancelled' | 'failed' | 'interrupted'
  duration_ms: number
}

/** SSE 事件信封。data 的具体形状由 type 决定，消费处窄化。 */
export interface TradingDeskEvent {
  type: EventType
  run_id: string
  seq: number
  ts: number
  data: Record<string, unknown>
}

export type ControlAction = 'pause' | 'resume' | 'inject' | 'cancel'

export async function createRun(ticker: string, tradeDate?: string): Promise<string> {
  const { data } = await apiClient.post<{ run_id: string }>('/api/v1/trading-desk/runs', {
    ticker,
    trade_date: tradeDate ?? null,
  })
  return data.run_id
}

export async function controlRun(
  runId: string,
  action: ControlAction,
  text?: string,
): Promise<void> {
  await apiClient.post(`/api/v1/trading-desk/runs/${runId}/control`, { action, text: text ?? null })
}

/** 一条已解析的 SSE 帧：id 用于断线续读，event 是载荷。 */
export interface SseFrame {
  id: string | null
  event: TradingDeskEvent
}

/**
 * 订阅事件流。
 *
 * 后端每帧形如 `id: <streamId>\ndata: <json>\n\n`，两行都要解析——
 * 只取 data 会丢掉断线重连所需的 Last-Event-ID。
 *
 * @param runId 运行 ID
 * @param lastEventId 上次收到的 Stream ID，断线重连时传入
 * @param signal 用于取消订阅（组件卸载 / 用户重新开始）
 */
export async function* streamRun(
  runId: string,
  lastEventId: string | null,
  signal: AbortSignal,
): AsyncGenerator<SseFrame> {
  const headers: Record<string, string> = {}
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  if (lastEventId) headers['Last-Event-ID'] = lastEventId

  const response = await fetch(`${BASE_URL}/api/v1/trading-desk/runs/${runId}/stream`, {
    headers,
    signal,
  })
  if (!response.ok) throw new Error(`事件流连接失败（${response.status}）`)

  const reader = response.body?.getReader()
  if (!reader) throw new Error('当前浏览器不支持流式读取')

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分帧；最后一段可能是半包，留在 buffer 里等下一轮
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''

      for (const raw of frames) {
        const frame = parseFrame(raw)
        if (frame) yield frame
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseFrame(raw: string): SseFrame | null {
  let id: string | null = null
  let data: string | null = null

  for (const line of raw.split('\n')) {
    if (line.startsWith('id: ')) id = line.slice(4).trim()
    else if (line.startsWith('data: ')) data = line.slice(6).trim()
  }
  if (!data) return null

  try {
    return { id, event: JSON.parse(data) as TradingDeskEvent }
  } catch {
    return null // 坏行直接丢，不要让一条脏数据掐断整条流
  }
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/api/trading_desk.ts
git commit -m "feat(trading-desk/web): API 层与事件类型"
```

---

## Task 2: Zustand store 与事件 reducer

这是前端唯一有真实逻辑的地方。`applyEvent` 写成不依赖 React 的纯函数。

**Files:**
- Create: `frontend/lib/store/trading_desk.ts`

- [ ] **Step 1: 实现 store**

创建 `frontend/lib/store/trading_desk.ts`：

```ts
/**
 * 交易台状态：把 SSE 事件流折叠成 UI 状态。
 *
 * 设计原则：store 是唯一真源。组件不自己拼 token、不自己算共识——
 * 所有派生状态在 applyEvent 里算好。applyEvent 是纯函数（不依赖 React），
 * 将来引入测试框架时可直接覆盖。
 */
import { create } from 'zustand'
import type {
  ConsensusData,
  DebateTurnData,
  EngineCapabilities,
  Polarity,
  RunStartedData,
  SignalData,
  StageDescriptor,
  TradingDeskEvent,
  TurnStartedData,
  VerdictData,
} from '@/lib/api/trading_desk'

export type RunStatus = 'idle' | 'running' | 'paused' | 'completed' | 'cancelled' | 'failed'
export type StageStatus = 'pending' | 'active' | 'done'

export interface Turn {
  turnId: string
  stageId: string
  name: string
  role: string
  avatar: string
  text: string
  tools: string[]
  done: boolean
  /** 人工意见卡片，与 agent 卡片区分渲染 */
  human: boolean
  /** 辩论元数据；非辩论卡片为 null */
  debate: { debateId: string; side: string; sideLabel: string; polarity: Polarity; round: number } | null
  signal: { dir: Polarity; conf: number; extracted: boolean } | null
}

export interface AuditEntry {
  who: string
  human: boolean
  excerpt: string
}

export interface TradingDeskState {
  runId: string | null
  status: RunStatus
  ticker: string
  engine: string
  capabilities: EngineCapabilities
  stages: StageDescriptor[]
  stageStatus: Record<string, StageStatus>
  stageSignal: Record<string, { dir: Polarity; conf: number }>
  turns: Turn[]
  signals: Array<{ name: string; dir: Polarity; conf: number; extracted: boolean }>
  consensus: ConsensusData | null
  verdict: VerdictData | null
  lastEventId: string | null
  lastSeq: number
  error: string | null
  durationMs: number | null

  applyEvent: (event: TradingDeskEvent, eventId: string | null) => void
  startRun: (runId: string, ticker: string) => void
  reset: () => void
}

const EMPTY_CAPABILITIES: EngineCapabilities = {
  supports_pause: false,
  supports_inject: false,
  supports_resume_after_restart: false,
}

const initial = {
  runId: null,
  status: 'idle' as RunStatus,
  ticker: '',
  engine: '',
  capabilities: EMPTY_CAPABILITIES,
  stages: [] as StageDescriptor[],
  stageStatus: {} as Record<string, StageStatus>,
  stageSignal: {} as Record<string, { dir: Polarity; conf: number }>,
  turns: [] as Turn[],
  signals: [] as Array<{ name: string; dir: Polarity; conf: number; extracted: boolean }>,
  consensus: null,
  verdict: null,
  lastEventId: null,
  lastSeq: 0,
  error: null,
  durationMs: null,
}

/** 从事件流折叠出下一份状态。纯函数，不碰 React。 */
export function reduceEvent(state: TradingDeskState, event: TradingDeskEvent): Partial<TradingDeskState> {
  switch (event.type) {
    case 'run.started': {
      const d = event.data as unknown as RunStartedData
      return {
        ticker: d.ticker,
        engine: d.engine,
        capabilities: d.capabilities,
        stages: d.stages,
        stageStatus: Object.fromEntries(d.stages.map((s) => [s.id, 'pending' as StageStatus])),
        status: 'running',
      }
    }

    case 'stage.active':
      return {
        stageStatus: { ...state.stageStatus, [event.data.stage_id as string]: 'active' },
      }

    case 'stage.done':
      return {
        stageStatus: { ...state.stageStatus, [event.data.stage_id as string]: 'done' },
      }

    case 'turn.started': {
      const d = event.data as unknown as TurnStartedData
      const turn: Turn = {
        turnId: d.turn_id,
        stageId: d.stage_id,
        name: d.name,
        role: d.role,
        avatar: d.avatar,
        text: '',
        tools: [],
        done: false,
        human: false,
        debate: null,
        signal: null,
      }
      return { turns: [...state.turns, turn] }
    }

    case 'debate.turn': {
      const d = event.data as unknown as DebateTurnData
      return {
        turns: state.turns.map((t) =>
          t.turnId === d.turn_id
            ? {
                ...t,
                debate: {
                  debateId: d.debate_id,
                  side: d.side,
                  sideLabel: d.side_label,
                  polarity: d.polarity,
                  round: d.round,
                },
              }
            : t,
        ),
      }
    }

    case 'agent.tool_call':
      return {
        turns: state.turns.map((t) =>
          t.turnId === event.data.turn_id ? { ...t, tools: [...t.tools, event.data.tool as string] } : t,
        ),
      }

    case 'agent.token':
      return {
        turns: state.turns.map((t) =>
          t.turnId === event.data.turn_id ? { ...t, text: t.text + (event.data.text as string) } : t,
        ),
      }

    case 'turn.done':
      return {
        turns: state.turns.map((t) => (t.turnId === event.data.turn_id ? { ...t, done: true } : t)),
      }

    case 'agent.signal': {
      const d = event.data as unknown as SignalData
      return {
        signals: [...state.signals, { name: d.name, dir: d.dir, conf: d.conf, extracted: d.extracted }],
        stageSignal: { ...state.stageSignal, [d.stage_id]: { dir: d.dir, conf: d.conf } },
        turns: state.turns.map((t) =>
          t.turnId === d.turn_id ? { ...t, signal: { dir: d.dir, conf: d.conf, extracted: d.extracted } } : t,
        ),
      }
    }

    case 'human.note': {
      const turn: Turn = {
        turnId: `human-${event.seq}`,
        stageId: '',
        name: '你',
        role: '人工意见',
        avatar: '你',
        text: event.data.text as string,
        tools: [],
        done: true,
        human: true,
        debate: null,
        signal: null,
      }
      return { turns: [...state.turns, turn] }
    }

    case 'consensus.update':
      return { consensus: event.data as unknown as ConsensusData }

    case 'run.paused':
      return { status: 'paused' }

    case 'run.resumed':
      return { status: 'running' }

    case 'verdict':
      return { verdict: event.data as unknown as VerdictData }

    case 'run.finished':
      return {
        status: event.data.status as RunStatus,
        durationMs: event.data.duration_ms as number,
      }

    case 'error':
      return { error: event.data.message as string }

    default:
      return {}
  }
}

/** 审计链由 turn 序列派生，不是独立事件。人工意见显式标注，使人为干预可追溯。 */
export function buildAuditChain(turns: Turn[]): AuditEntry[] {
  return turns
    .filter((t) => t.text.trim().length > 0)
    .map((t) => ({
      who: t.human ? '你' : t.debate ? `${t.name}（第 ${t.debate.round} 轮）` : t.name,
      human: t.human,
      excerpt: t.text.length > 40 ? `${t.text.slice(0, 40)}…` : t.text,
    }))
}

export const useTradingDeskStore = create<TradingDeskState>((set, get) => ({
  ...initial,

  applyEvent: (event, eventId) => {
    const state = get()
    // seq 单调递增，重连时可能重放已处理过的事件，直接丢弃
    if (event.seq <= state.lastSeq) return
    set({ ...reduceEvent(state, event), lastEventId: eventId ?? state.lastEventId, lastSeq: event.seq })
  },

  startRun: (runId, ticker) => set({ ...initial, runId, ticker, status: 'running' }),

  reset: () => set({ ...initial }),
}))
```

- [ ] **Step 2: 类型检查与 lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/store/trading_desk.ts
git commit -m "feat(trading-desk/web): 事件 reducer 与 store"
```

---

## Task 3: 信号 chip 与流程条

**Files:**
- Create: `frontend/components/trading_desk/SignalChip.tsx`
- Create: `frontend/components/trading_desk/PipelinePanel.tsx`

- [ ] **Step 1: SignalChip**

创建 `frontend/components/trading_desk/SignalChip.tsx`：

```tsx
import type { Polarity } from '@/lib/api/trading_desk'

const STYLE: Record<Polarity, { box: string; dot: string; label: string }> = {
  bull: { box: 'bg-green-50 text-green-700', dot: 'bg-green-600', label: '看多' },
  bear: { box: 'bg-red-50 text-red-600', dot: 'bg-red-500', label: '看空' },
  neutral: { box: 'bg-amber-50 text-amber-700', dot: 'bg-amber-600', label: '中性' },
}

export default function SignalChip({
  dir,
  conf,
  extracted = false,
}: {
  dir: Polarity
  conf: number
  extracted?: boolean
}) {
  const s = STYLE[dir]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${s.box}`}
      // extracted 表示信号是我们从报告里抽取的，而非引擎原生产出——
      // 不标出来的话，用户会以为这是 agent 自己给的置信度
      title={extracted ? '由报告文本抽取得出，非 agent 原生输出' : undefined}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label} · {conf}
      {extracted && <span className="text-[10px] opacity-60">抽</span>}
    </span>
  )
}
```

- [ ] **Step 2: PipelinePanel**

创建 `frontend/components/trading_desk/PipelinePanel.tsx`：

```tsx
'use client'

import { Check, Loader2 } from 'lucide-react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'
import SignalChip from './SignalChip'

export default function PipelinePanel() {
  const stages = useTradingDeskStore((s) => s.stages)
  const stageStatus = useTradingDeskStore((s) => s.stageStatus)
  const stageSignal = useTradingDeskStore((s) => s.stageSignal)

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        交易台成员
      </div>

      {stages.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-400">开始分析后显示阵容</p>
      ) : (
        <div className="flex gap-2 overflow-x-auto sm:block sm:overflow-visible">
          {stages.map((stage) => {
            const status = stageStatus[stage.id] ?? 'pending'
            const signal = stageSignal[stage.id]
            return (
              <div
                key={stage.id}
                className={`flex w-44 flex-none gap-2.5 rounded-lg p-2 transition-colors sm:w-auto ${
                  status === 'active' ? 'bg-blue-50' : ''
                }`}
              >
                <div className="mt-0.5 flex-none">
                  {status === 'done' ? (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-600">
                      <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
                    </span>
                  ) : status === 'active' ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                  ) : (
                    <span className="block h-4 w-4 rounded-full border-2 border-gray-300" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div
                    className={`truncate text-[13px] font-semibold ${
                      status === 'pending' ? 'text-gray-400' : 'text-gray-900'
                    }`}
                  >
                    {stage.name}
                  </div>
                  <div className="truncate font-mono text-[10px] text-gray-400">{stage.role}</div>
                  {signal && (
                    <div className="mt-1.5">
                      <SignalChip dir={signal.dir} conf={signal.conf} />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 检查**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 4: 提交**

```bash
git add frontend/components/trading_desk/
git commit -m "feat(trading-desk/web): 信号 chip 与流程条"
```

---

## Task 4: 推理流

**Files:**
- Create: `frontend/components/trading_desk/TurnCard.tsx`
- Create: `frontend/components/trading_desk/StreamPanel.tsx`

- [ ] **Step 1: TurnCard**

创建 `frontend/components/trading_desk/TurnCard.tsx`：

```tsx
import type { Turn } from '@/lib/store/trading_desk'
import SignalChip from './SignalChip'

/** 辩论卡片按 polarity 分色分栏：前端不必认识具体门派，
 *  因此同一套渲染既能画多空二元辩论，也能画激进/中立/保守三方辩论。 */
function toneOf(turn: Turn): { card: string; avatar: string; name: string; indent: string } {
  if (turn.human) {
    return {
      card: 'border-blue-500 bg-blue-50/70',
      avatar: 'bg-blue-100 text-blue-700 border-blue-300',
      name: 'text-blue-700',
      indent: '',
    }
  }
  switch (turn.debate?.polarity) {
    case 'bull':
      return {
        card: 'border-green-200 bg-gradient-to-b from-green-50/70 to-white',
        avatar: 'bg-green-100 text-green-700 border-green-300',
        name: 'text-green-700',
        indent: '',
      }
    case 'bear':
      return {
        card: 'border-red-200 bg-gradient-to-b from-red-50/70 to-white',
        avatar: 'bg-red-100 text-red-700 border-red-300',
        name: 'text-red-600',
        indent: 'ml-0 sm:ml-8',
      }
    case 'neutral':
      return {
        card: 'border-amber-200 bg-gradient-to-b from-amber-50/70 to-white',
        avatar: 'bg-amber-100 text-amber-700 border-amber-300',
        name: 'text-amber-700',
        indent: 'ml-0 sm:ml-4',
      }
    default:
      return {
        card: 'border-gray-200 bg-gray-50/60',
        avatar: 'bg-gray-100 text-gray-500 border-gray-200',
        name: 'text-gray-900',
        indent: '',
      }
  }
}

export default function TurnCard({ turn, streaming }: { turn: Turn; streaming: boolean }) {
  const tone = toneOf(turn)

  return (
    <div className={`rounded-xl border p-3.5 motion-safe:animate-in motion-safe:fade-in ${tone.card} ${tone.indent}`}>
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`flex h-6 w-6 flex-none items-center justify-center rounded-md border font-mono text-[10px] font-bold ${tone.avatar}`}
        >
          {turn.avatar}
        </span>
        <span className={`text-[13px] font-semibold ${tone.name}`}>{turn.name}</span>
        {turn.role && (
          <span className="ml-auto font-mono text-[10px] text-gray-400">{turn.role}</span>
        )}
      </div>

      {turn.tools.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {turn.tools.map((tool, i) => (
            <span
              key={`${tool}-${i}`}
              className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] text-blue-600"
            >
              ⚙ {tool}
            </span>
          ))}
        </div>
      )}

      <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-gray-700">
        {turn.text}
        {streaming && (
          <span className="ml-0.5 inline-block h-3.5 w-[3px] translate-y-[2px] bg-blue-600 motion-safe:animate-pulse" />
        )}
      </p>

      {turn.signal && (
        <div className="mt-2">
          <SignalChip dir={turn.signal.dir} conf={turn.signal.conf} extracted={turn.signal.extracted} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: StreamPanel**

创建 `frontend/components/trading_desk/StreamPanel.tsx`：

```tsx
'use client'

import { useEffect, useRef } from 'react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'
import TurnCard from './TurnCard'

export default function StreamPanel() {
  const turns = useTradingDeskStore((s) => s.turns)
  const status = useTradingDeskStore((s) => s.status)
  const bottomRef = useRef<HTMLDivElement>(null)

  // 跟随最新内容滚动。用 turns 长度与最后一张卡片的文本长度做依赖，
  // 这样流式追加 token 时也会持续跟随。
  const tail = turns.length > 0 ? turns[turns.length - 1].text.length : 0
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [turns.length, tail])

  // 正在流式输出的卡片：最后一张尚未 turn.done 的
  const streamingId =
    status === 'running' ? turns.find((t) => !t.done)?.turnId ?? null : null

  return (
    <div className="flex min-h-[28rem] flex-col rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        实时推理
      </div>

      {turns.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6 py-16 text-center">
          <div>
            <p className="text-sm font-semibold text-gray-500">交易台还很安静。</p>
            <p className="mt-2 text-[13px] leading-relaxed text-gray-400">
              输入标的、点「开始分析」。
              <br />
              看每个 agent 实时推理、辩论、给出结论。
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-2.5 overflow-y-auto">
          {turns.map((turn) => (
            <TurnCard key={turn.turnId} turn={turn} streaming={turn.turnId === streamingId} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 检查并提交**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/components/trading_desk/
git commit -m "feat(trading-desk/web): 推理流与辩论卡片"
```

---

## Task 5: 决策面板

**Files:**
- Create: `frontend/components/trading_desk/ConsensusMeter.tsx`
- Create: `frontend/components/trading_desk/VerdictCard.tsx`
- Create: `frontend/components/trading_desk/DecisionPanel.tsx`

- [ ] **Step 1: ConsensusMeter**

创建 `frontend/components/trading_desk/ConsensusMeter.tsx`：

```tsx
'use client'

import { useTradingDeskStore } from '@/lib/store/trading_desk'

export default function ConsensusMeter() {
  const consensus = useTradingDeskStore((s) => s.consensus)
  const total = consensus ? consensus.bull + consensus.neutral + consensus.bear : 0
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0)

  return (
    <div>
      <div className="mb-1.5 flex justify-between font-mono text-[10px] text-gray-400">
        <span>共识</span>
        <span>
          {consensus ? `多${consensus.bull} 中${consensus.neutral} 空${consensus.bear} · ${consensus.lean}` : '—'}
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-gray-100">
        <span
          className="h-full bg-green-600 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.bull ?? 0)}%` }}
        />
        <span
          className="h-full bg-amber-500 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.neutral ?? 0)}%` }}
        />
        <span
          className="h-full bg-red-500 transition-[width] duration-500"
          style={{ width: `${pct(consensus?.bear ?? 0)}%` }}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: VerdictCard**

创建 `frontend/components/trading_desk/VerdictCard.tsx`：

```tsx
'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { buildAuditChain, useTradingDeskStore } from '@/lib/store/trading_desk'

const ACTION: Record<string, { label: string; color: string }> = {
  BUY: { label: '买入', color: 'text-green-600' },
  SELL: { label: '卖出', color: 'text-red-500' },
  HOLD: { label: '观望', color: 'text-amber-600' },
}

/** 置信度数字滚动到目标值。尊重 prefers-reduced-motion：直接显示终值。 */
function useCountUp(target: number | null): number {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (target === null) {
      setValue(0)
      return
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setValue(target)
      return
    }
    let current = 0
    const timer = window.setInterval(() => {
      current = Math.min(current + 2, target)
      setValue(current)
      if (current >= target) window.clearInterval(timer)
    }, 18)
    return () => window.clearInterval(timer)
  }, [target])

  return value
}

export default function VerdictCard() {
  const verdict = useTradingDeskStore((s) => s.verdict)
  const turns = useTradingDeskStore((s) => s.turns)
  const [auditOpen, setAuditOpen] = useState(false)

  const confPct = verdict ? Math.round(verdict.confidence * 100) : null
  const animatedConf = useCountUp(confPct)
  const action = verdict ? ACTION[verdict.signal] : null
  const audit = buildAuditChain(turns)

  return (
    <div
      className={`rounded-xl border p-4 ${
        verdict ? 'border-gray-200 bg-gray-50/70' : 'border-gray-100 bg-gray-50/40 opacity-60'
      }`}
    >
      <div className="flex items-baseline justify-between">
        <span className={`text-xl font-extrabold ${action?.color ?? 'text-gray-400'}`}>
          {action?.label ?? '—'}
        </span>
        <span className="font-mono text-[11px] text-gray-500">
          置信度 <b className="text-sm text-gray-900">{verdict ? `${animatedConf}%` : '—'}</b>
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Field label="仓位" value={verdict ? `${(verdict.size_fraction * 100).toFixed(1)}%` : '—'} />
        <Field label="止损" value={verdict?.stop_loss != null ? String(verdict.stop_loss) : '—'} />
        <Field label="目标价" value={verdict?.target_price != null ? String(verdict.target_price) : '—'} />
        <Field
          label="周期"
          value={verdict?.time_horizon_days != null ? `${verdict.time_horizon_days} 天` : '—'}
        />
      </div>

      {/* 引擎在 JSON 解析失败走 fallback 时会置位 warning_message。
          必须显式展示——否则用户会把降级解析出的结论当作正常结论。 */}
      {verdict?.warning_message && (
        <div className="mt-3 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none text-amber-600" />
          <p className="text-[11.5px] leading-relaxed text-amber-800">
            结论解析降级：{verdict.warning_message}
          </p>
        </div>
      )}

      {verdict?.rationale && (
        <p className="mt-3 border-t border-gray-200 pt-3 text-[12px] leading-relaxed text-gray-600">
          {verdict.rationale}
        </p>
      )}

      {audit.length > 0 && (
        <div className="mt-3 border-t border-gray-200 pt-2">
          <button
            type="button"
            onClick={() => setAuditOpen((v) => !v)}
            className="flex items-center gap-1 font-mono text-[10px] text-blue-600 hover:text-blue-700"
          >
            <ChevronRight className={`h-3 w-3 transition-transform ${auditOpen ? 'rotate-90' : ''}`} />
            审计链（{audit.length} 步）
          </button>
          {auditOpen && (
            <ol className="mt-2 space-y-1.5 pl-4 text-[11px] leading-relaxed text-gray-500">
              {audit.map((entry, i) => (
                <li key={i} className="list-decimal">
                  <b className={entry.human ? 'text-blue-600' : 'text-gray-700'}>{entry.who}</b>
                  {' —— '}
                  {entry.excerpt}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] text-gray-400">{label}</div>
      <div className="mt-0.5 font-mono text-[13px] font-semibold text-gray-900">{value}</div>
    </div>
  )
}
```

- [ ] **Step 3: DecisionPanel**

创建 `frontend/components/trading_desk/DecisionPanel.tsx`：

```tsx
'use client'

import { useTradingDeskStore } from '@/lib/store/trading_desk'
import ConsensusMeter from './ConsensusMeter'
import SignalChip from './SignalChip'
import VerdictCard from './VerdictCard'

export default function DecisionPanel() {
  const signals = useTradingDeskStore((s) => s.signals)

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4">
      <div className="mb-3 font-mono text-[11px] font-bold uppercase tracking-wider text-gray-400">
        决策
      </div>

      <div className="flex flex-col gap-4">
        <ConsensusMeter />

        {signals.length > 0 && (
          <div className="flex flex-col gap-2">
            {signals.map((s, i) => (
              <div key={`${s.name}-${i}`} className="flex items-center justify-between gap-2">
                <span className="truncate text-[12px] text-gray-500">{s.name}</span>
                <SignalChip dir={s.dir} conf={s.conf} extracted={s.extracted} />
              </div>
            ))}
          </div>
        )}

        <VerdictCard />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 检查并提交**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/components/trading_desk/
git commit -m "feat(trading-desk/web): 共识条与裁决卡"
```

---

## Task 6: 顶栏与控制

**Files:**
- Create: `frontend/components/trading_desk/TradingDeskTopbar.tsx`

- [ ] **Step 1: 实现**

创建 `frontend/components/trading_desk/TradingDeskTopbar.tsx`：

```tsx
'use client'

import { useState, type FormEvent } from 'react'
import { Pause, Play, Square, MessageSquarePlus } from 'lucide-react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'

const STATUS_TEXT: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  cancelled: '已取消',
  failed: '已失败',
}

export default function TradingDeskTopbar({
  ticker,
  onTickerChange,
  onStart,
  onPause,
  onResume,
  onCancel,
  onInject,
  busy,
}: {
  ticker: string
  onTickerChange: (v: string) => void
  onStart: () => void
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onInject: (text: string) => void
  busy: boolean
}) {
  const status = useTradingDeskStore((s) => s.status)
  const capabilities = useTradingDeskStore((s) => s.capabilities)
  const [injectOpen, setInjectOpen] = useState(false)
  const [note, setNote] = useState('')

  const live = status === 'running' || status === 'paused'

  const submitNote = (e: FormEvent) => {
    e.preventDefault()
    const text = note.trim()
    if (!text) return
    onInject(text)
    setNote('')
    setInjectOpen(false)
  }

  return (
    <div className="mb-4 border-b border-gray-200 pb-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-gray-900">交易台</h1>
          <p className="font-mono text-[11px] text-gray-400">多智能体分析</p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center overflow-hidden rounded-lg border border-gray-300 bg-white">
            <span className="pl-3 font-mono text-xs text-gray-400">$</span>
            <input
              value={ticker}
              onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !live && !busy) onStart()
              }}
              maxLength={10}
              spellCheck={false}
              disabled={live}
              placeholder="NVDA"
              className="w-24 bg-transparent px-2 py-2 font-mono text-sm font-semibold uppercase text-gray-900 outline-none disabled:text-gray-400"
            />
          </div>

          <button
            type="button"
            onClick={onStart}
            disabled={live || busy || !ticker.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {status === 'idle' ? '开始分析' : live ? '分析中' : '重新分析'}
          </button>

          {capabilities.supports_pause && (
            <button
              type="button"
              onClick={status === 'paused' ? onResume : onPause}
              disabled={!live || busy}
              title={capabilities.supports_pause ? undefined : '当前引擎不支持暂停'}
              className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] font-semibold text-gray-600 transition hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {status === 'paused' ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
              {status === 'paused' ? '继续' : '暂停'}
            </button>
          )}

          {capabilities.supports_inject && (
            <button
              type="button"
              onClick={() => setInjectOpen((v) => !v)}
              disabled={!live || busy}
              className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] font-semibold text-gray-600 transition hover:border-blue-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MessageSquarePlus className="h-3.5 w-3.5" />
              注入意见
            </button>
          )}

          {live && (
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-[13px] font-semibold text-gray-500 transition hover:border-red-300 hover:text-red-500 disabled:opacity-40"
            >
              <Square className="h-3 w-3" />
              停止
            </button>
          )}

          <span className="flex items-center gap-1.5 font-mono text-[11px] text-gray-500">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                status === 'running'
                  ? 'bg-blue-600 motion-safe:animate-pulse'
                  : status === 'paused'
                    ? 'bg-amber-500'
                    : status === 'failed'
                      ? 'bg-red-500'
                      : 'bg-gray-300'
              }`}
            />
            {STATUS_TEXT[status] ?? status}
          </span>
        </div>
      </div>

      {injectOpen && (
        <form onSubmit={submitNote} className="mt-3 flex gap-2">
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="给交易台补一条上下文 —— 例如「把出口管制风险的权重调高」"
            className="flex-1 rounded-lg border border-blue-400 bg-white px-3 py-2 text-[13px] text-gray-900 outline-none placeholder:text-gray-400"
          />
          <button
            type="submit"
            className="rounded-lg bg-blue-600 px-4 py-2 text-[13px] font-semibold text-white hover:bg-blue-700"
          >
            加入
          </button>
          <button
            type="button"
            onClick={() => {
              setInjectOpen(false)
              setNote('')
            }}
            className="rounded-lg px-3 py-2 text-[13px] font-semibold text-gray-500 hover:text-gray-700"
          >
            取消
          </button>
        </form>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 检查并提交**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/components/trading_desk/TradingDeskTopbar.tsx
git commit -m "feat(trading-desk/web): 顶栏与控制交互"
```

---

## Task 7: 页面组装与 SSE 生命周期

**Files:**
- Create: `frontend/app/trading-desk/page.tsx`

- [ ] **Step 1: 实现页面**

创建 `frontend/app/trading-desk/page.tsx`：

```tsx
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import DashboardShell from '@/components/layout/DashboardShell'
import DecisionPanel from '@/components/trading_desk/DecisionPanel'
import PipelinePanel from '@/components/trading_desk/PipelinePanel'
import StreamPanel from '@/components/trading_desk/StreamPanel'
import TradingDeskTopbar from '@/components/trading_desk/TradingDeskTopbar'
import { controlRun, createRun, streamRun, type ControlAction } from '@/lib/api/trading_desk'
import { getApiErrorMessage } from '@/lib/api/client'
import { useTradingDeskStore } from '@/lib/store/trading_desk'

export default function TradingDeskPage() {
  const [ticker, setTicker] = useState('NVDA')
  const [busy, setBusy] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)

  const runId = useTradingDeskStore((s) => s.runId)
  const storeError = useTradingDeskStore((s) => s.error)
  const applyEvent = useTradingDeskStore((s) => s.applyEvent)
  const startRunInStore = useTradingDeskStore((s) => s.startRun)

  const abortRef = useRef<AbortController | null>(null)

  // 组件卸载时断开事件流，避免离开页面后仍在后台读取
  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  const consume = useCallback(
    async (id: string) => {
      // 断线自动重连：用 store 里的 lastEventId 续读，不会漏也不会重
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const controller = new AbortController()
        abortRef.current = controller
        try {
          const lastId = useTradingDeskStore.getState().lastEventId
          for await (const frame of streamRun(id, lastId, controller.signal)) {
            applyEvent(frame.event, frame.id)
          }
          return
        } catch (err) {
          if (controller.signal.aborted) return
          const finished = useTradingDeskStore.getState().status
          if (finished !== 'running' && finished !== 'paused') return
          if (attempt === 2) {
            setPageError(`事件流中断：${getApiErrorMessage(err)}`)
            return
          }
          await new Promise((r) => setTimeout(r, 800 * (attempt + 1)))
        }
      }
    },
    [applyEvent],
  )

  const handleStart = useCallback(async () => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return

    abortRef.current?.abort()
    setPageError(null)
    setBusy(true)
    try {
      const id = await createRun(symbol)
      startRunInStore(id, symbol)
      void consume(id)
    } catch (err) {
      setPageError(getApiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }, [ticker, consume, startRunInStore])

  const control = useCallback(
    async (action: ControlAction, text?: string) => {
      if (!runId) return
      setBusy(true)
      try {
        await controlRun(runId, action, text)
      } catch (err) {
        setPageError(getApiErrorMessage(err))
      } finally {
        setBusy(false)
      }
    },
    [runId],
  )

  const error = pageError ?? storeError

  return (
    <DashboardShell>
      <TradingDeskTopbar
        ticker={ticker}
        onTickerChange={setTicker}
        onStart={handleStart}
        onPause={() => void control('pause')}
        onResume={() => void control('resume')}
        onCancel={() => void control('cancel')}
        onInject={(text) => void control('inject', text)}
        busy={busy}
      />

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[15rem_1fr_19rem]">
        <PipelinePanel />
        <StreamPanel />
        <DecisionPanel />
      </div>

      <p className="mt-6 border-t border-gray-200 pt-4 text-center font-mono text-[11px] text-gray-400">
        研究 / 分析用途，非投资建议，不执行真实交易。agent 观点带置信度，不代表事实。
      </p>
    </DashboardShell>
  )
}
```

- [ ] **Step 2: 确认 `getApiErrorMessage` 已导出**

```bash
cd frontend && grep -n "export function getApiErrorMessage\|export const getApiErrorMessage" lib/api/client.ts
```

预期：有一行输出。若无，改用 `lib/api/client.ts` 中实际导出的错误提取函数名。

- [ ] **Step 3: 检查并提交**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/app/trading-desk/
git commit -m "feat(trading-desk/web): 页面组装与 SSE 生命周期"
```

---

## Task 8: 注册导航并验收

**Files:**
- Modify: `frontend/components/layout/TopNav.tsx`

- [ ] **Step 1: 加导航入口**

在 `frontend/components/layout/TopNav.tsx` 的 lucide-react import 中加入 `Gavel`，然后在「AI 工具」分组的 `items` 数组开头加入：

```tsx
      { href: '/trading-desk',    label: '交易台',   icon: Gavel },
```

改完后该分组形如：

```tsx
  {
    label: 'AI 工具',
    icon: Sparkles,
    items: [
      { href: '/trading-desk',    label: '交易台',  icon: Gavel },
      { href: '/chat',            label: 'AI 对话', icon: MessageSquare },
      { href: '/skill-generator', label: '因子探索', icon: FlaskConical },
    ],
  },
```

- [ ] **Step 2: 全量检查**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

预期：三项均通过。`npm run build` 是关键——它会暴露 tsc 查不出的 App Router 层面问题。

- [ ] **Step 3: 提交并推送**

```bash
git add frontend/components/layout/TopNav.tsx
git commit -m "feat(trading-desk/web): 注册导航入口"
git push origin master
```

- [ ] **Step 4: 线上验收**

等待 Vercel 部署完成后，访问 `https://deepalpha.club/trading-desk`，逐项核对：

| 核对项 | 预期 |
|---|---|
| 空态 | 「交易台还很安静。」+ 引导文案 |
| 点「开始分析」 | 流程条出现 7 个节点；第一个转圈 |
| 流式 | 文字逐字出现，末尾有闪烁光标 |
| 工具 chip | 分析师卡片上方出现 `⚙ ohlcv.get` 等蓝色 chip |
| 节点完成 | 转圈变绿色打勾，右侧挂上信号 chip |
| 辩论 | 多头绿色靠左、空头红色右移错位，标注轮次 |
| 共识条 | 三色按比例填充，带过渡动画 |
| 裁决卡 | 「买入」绿色大字，置信度数字滚动到 66% |
| 审计链 | 点开后列出各 agent 发言摘要 |
| 暂停 | 状态灯变琥珀色，流停在节点边界（不截断半句话） |
| 注入意见 | 蓝色「你 / 人工意见」卡片插入流中 |
| 继续 | 流恢复推进直到裁决 |
| 刷新页面 | 运行仍在后台跑（当前不自动重连，属已知限制） |
| 窄屏 | 三栏堆叠，流程条转为横向滚动 |
| 免责声明 | 页面底部常驻 |

---

## 验收标准

1. `npx tsc --noEmit`、`npm run lint`、`npm run build` 三项通过
2. 线上 `/trading-desk` 完成上表全部核对项
3. 「AI 工具」导航下出现「交易台」入口

## 已知限制（不在本计划范围）

- **刷新页面不自动接回运行。** run_id 只在内存里，刷新即丢。要修需要把 run_id 存进 URL 或 localStorage——等计划三的历史列表落地后一并处理更自然。
- **无前端测试。** 见开头说明。`reduceEvent` 与 `buildAuditChain` 已写成纯函数，引入 vitest 后可直接覆盖。

## 下一步

计划三：TradingAgentsEngine + 信号抽取 + 落库回放（spec 阶段 3-4）。
