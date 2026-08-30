'use client'

import { useState, type FormEvent } from 'react'
import { MessageSquarePlus, Pause, Play, Square } from 'lucide-react'
import { useTradingDeskStore } from '@/lib/store/trading_desk'

type Market = 'US' | 'HK' | 'SH' | 'SZ'

const STATUS_TEXT: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  cancelled: '已取消',
  failed: '已失败',
}

const MARKET_OPTIONS: { value: Market; label: string; placeholder: string }[] = [
  { value: 'US', label: '美股', placeholder: 'NVDA' },
  { value: 'HK', label: '港股', placeholder: '0700' },
  { value: 'SH', label: '沪 A', placeholder: '600519' },
  { value: 'SZ', label: '深 A', placeholder: '000001' },
]

export default function TradingDeskTopbar({
  ticker,
  onTickerChange,
  market,
  onMarketChange,
  onStart,
  onPause,
  onResume,
  onCancel,
  onInject,
  busy,
}: {
  ticker: string
  onTickerChange: (v: string) => void
  market: Market
  onMarketChange: (m: Market) => void
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
  const placeholder = MARKET_OPTIONS.find((o) => o.value === market)?.placeholder ?? 'NVDA'

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
          <div
            className="flex overflow-hidden rounded-lg border border-gray-300 bg-white"
            role="radiogroup"
            aria-label="市场"
          >
            {MARKET_OPTIONS.map((opt) => {
              const active = opt.value === market
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={live}
                  onClick={() => onMarketChange(opt.value)}
                  className={`px-2.5 py-2 font-mono text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    active
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

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
              placeholder={placeholder}
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
