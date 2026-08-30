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
