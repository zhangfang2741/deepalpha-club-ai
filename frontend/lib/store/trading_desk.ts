/**
 * 交易台状态：把 SSE 事件流折叠成 UI 状态。
 *
 * 设计原则：store 是唯一真源。组件不自己拼 token、不自己算共识——
 * 所有派生状态在 reduceEvent 里算好。reduceEvent 是纯函数（不依赖 React），
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
  /** Anthropic extended thinking 推理链片段折叠。仅启用 thinking 时非空。 */
  thinking?: string
  tools: string[]
  done: boolean
  /** 人工意见卡片，与 agent 卡片区分渲染 */
  human: boolean
  /** 辩论元数据；非辩论卡片为 null */
  debate: {
    debateId: string
    side: string
    sideLabel: string
    polarity: Polarity
    round: number
  } | null
  signal: { dir: Polarity; conf: number; extracted: boolean } | null
}

export interface AuditEntry {
  who: string
  human: boolean
  excerpt: string
}

export interface SignalRow {
  name: string
  dir: Polarity
  conf: number
  extracted: boolean
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
  signals: SignalRow[]
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
  runId: null as string | null,
  status: 'idle' as RunStatus,
  ticker: '',
  engine: '',
  capabilities: EMPTY_CAPABILITIES,
  stages: [] as StageDescriptor[],
  stageStatus: {} as Record<string, StageStatus>,
  stageSignal: {} as Record<string, { dir: Polarity; conf: number }>,
  turns: [] as Turn[],
  signals: [] as SignalRow[],
  consensus: null as ConsensusData | null,
  verdict: null as VerdictData | null,
  lastEventId: null as string | null,
  lastSeq: 0,
  error: null as string | null,
  durationMs: null as number | null,
}

/** 从事件流折叠出下一份状态。纯函数，不碰 React。 */
export function reduceEvent(
  state: TradingDeskState,
  event: TradingDeskEvent,
): Partial<TradingDeskState> {
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
          t.turnId === event.data.turn_id
            ? { ...t, tools: [...t.tools, event.data.tool as string] }
            : t,
        ),
      }

    case 'agent.token':
      return {
        turns: state.turns.map((t) =>
          t.turnId === event.data.turn_id ? { ...t, text: t.text + (event.data.text as string) } : t,
        ),
      }

    case 'agent.think':
      return {
        turns: state.turns.map((t) =>
          t.turnId === event.data.turn_id
            ? { ...t, thinking: (t.thinking ?? '') + (event.data.text as string) }
            : t,
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
          t.turnId === d.turn_id
            ? { ...t, signal: { dir: d.dir, conf: d.conf, extracted: d.extracted } }
            : t,
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
    set({
      ...reduceEvent(state, event),
      lastEventId: eventId ?? state.lastEventId,
      lastSeq: event.seq,
    })
  },

  startRun: (runId, ticker) => set({ ...initial, runId, ticker, status: 'running' }),

  reset: () => set({ ...initial }),
}))
