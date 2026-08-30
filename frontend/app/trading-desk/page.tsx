'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { History } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import DecisionPanel from '@/components/trading_desk/DecisionPanel'
import PipelinePanel from '@/components/trading_desk/PipelinePanel'
import StreamPanel from '@/components/trading_desk/StreamPanel'
import TradingDeskTopbar from '@/components/trading_desk/TradingDeskTopbar'
import { getApiErrorMessage } from '@/lib/api/client'
import { controlRun, createRun, streamRun, type ControlAction } from '@/lib/api/trading_desk'
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
      // 无限重连：每次失败指数退避（cap 30s），run 进入终态时退出。
      // 后端 SSE 每 15s 发注释行保活，断线通常来自网络抖动或代理切断；
      // 静默退避恢复后用 store 里的 lastEventId 续读，不漏也不重。
      let backoffMs = 800
      while (true) {
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
          const status = useTradingDeskStore.getState().status
          if (status !== 'running' && status !== 'paused') return
          await new Promise((r) => setTimeout(r, backoffMs))
          backoffMs = Math.min(backoffMs * 2, 30_000)
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
        onStart={() => void handleStart()}
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

      <div className="mt-3 flex justify-center">
        <Link
          href="/trading-desk/history"
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-gray-600 transition hover:border-blue-300 hover:text-blue-600"
        >
          <History className="h-4 w-4" />
          查看历史运行
        </Link>
      </div>
    </DashboardShell>
  )
}
