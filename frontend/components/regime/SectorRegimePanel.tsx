'use client'

import { useEffect, useState, useCallback } from 'react'
import Spinner from '@/components/ui/Spinner'
import { LABEL_COLOR, labelZh, colorOf } from '@/components/regime/common'
import {
  fetchSectorRegimes,
  triggerSectorStage,
  type SectorRegimePoint,
} from '@/lib/api/regime'

function SectorTile({ s }: { s: SectorRegimePoint }) {
  const lab = s.confirmed_label ?? s.regime_label
  const c = colorOf(lab)
  const rs = s.rs_vs_market
  return (
    <div className="rounded-xl p-4 flex flex-col gap-1.5 border" style={{ background: `${c}0f`, borderColor: `${c}33` }}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-gray-800">{s.sector_name}</span>
        <span className="text-xs font-bold px-2 py-0.5 rounded-md" style={{ color: c, background: `${c}1f` }}>
          {labelZh(lab)}
        </span>
      </div>
      <div className="flex items-end justify-between">
        <div className="flex flex-col">
          <span className="text-[10px] text-gray-400 font-semibold">相对大盘</span>
          <span className="text-sm font-bold font-mono tabular-nums" style={{ color: (rs ?? 0) >= 0 ? LABEL_COLOR.risk_on : LABEL_COLOR.risk_off }}>
            {rs === null ? '—' : `${rs >= 0 ? '+' : ''}${(rs * 100).toFixed(1)}%`}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] text-gray-400 font-semibold">仓位系数</span>
          <span className="text-lg font-black font-mono tabular-nums text-gray-800">{s.factor_weight === null ? '—' : s.factor_weight.toFixed(2)}</span>
        </div>
      </div>
    </div>
  )
}

/**
 * 板块状态面板（行业级 regime）：可嵌入行业恐慌页作为一个 Tab。
 */
export default function SectorRegimePanel() {
  const [sectors, setSectors] = useState<SectorRegimePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetchSectorRegimes()
      setSectors(resp.sectors)
    } catch {
      setError('加载板块状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    try {
      await triggerSectorStage()
      await load()
    } catch {
      setError('重新计算失败（需登录且行情可用）')
    } finally {
      setRunning(false)
    }
  }

  const tradeDate = sectors[0]?.trade_date ?? null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-gray-500 leading-relaxed">
          每个 GICS 行业单独拟合 HMM，输出各自的逐利/观望/避险状态，按逐利程度排序 ·{' '}
          <span className="text-red-600 font-semibold">红=逐利</span>{' '}
          <span className="text-amber-600 font-semibold">橙=观望</span>{' '}
          <span className="text-green-600 font-semibold">绿=避险</span>
          {tradeDate && <span className="text-gray-400 font-mono ml-2">{tradeDate}</span>}
        </p>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-4 py-2 rounded-xl bg-gray-900 text-white text-sm font-bold hover:bg-gray-800 disabled:opacity-50 transition-all whitespace-nowrap"
        >
          {running ? '计算中…' : '重新计算'}
        </button>
      </div>

      {error && <div className="px-4 py-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-sm font-medium">{error}</div>}

      {loading ? (
        <div className="flex items-center justify-center h-[200px]">
          <Spinner size={40} />
        </div>
      ) : sectors.length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center">暂无板块数据，点「重新计算」触发行业级计算（需登录且行情可用）</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {sectors.map((s) => (
            <SectorTile key={s.sector} s={s} />
          ))}
        </div>
      )}
    </div>
  )
}
