'use client'

import { useEffect, useMemo, useState } from 'react'
import type { GICSValuationResponse, IndustryValuation, SectorWithIndustries } from '@/lib/api/valuation'
import { fetchGICSValuations } from '@/lib/api/valuation'
import Spinner from '@/components/ui/Spinner'
import SectorPEChart from './SectorPEChart'

type LabelEn =
  | 'extreme_undervalue'
  | 'undervalue'
  | 'neutral'
  | 'overvalue'
  | 'extreme_overvalue'
  | 'insufficient'

const LABEL_CONFIG: Record<LabelEn, { badge: string; text: string; bar: string; cn: string }> = {
  extreme_undervalue: { badge: 'bg-blue-700 text-white',        text: 'text-blue-700',   bar: 'bg-blue-700',   cn: '极度低估' },
  undervalue:         { badge: 'bg-blue-100 text-blue-700',     text: 'text-blue-600',   bar: 'bg-blue-400',   cn: '低估'     },
  neutral:            { badge: 'bg-slate-100 text-slate-500',   text: 'text-slate-400',  bar: 'bg-slate-300',  cn: '中性'     },
  overvalue:          { badge: 'bg-orange-100 text-orange-600', text: 'text-orange-500', bar: 'bg-orange-400', cn: '高估'     },
  extreme_overvalue:  { badge: 'bg-red-100 text-red-600',       text: 'text-red-500',    bar: 'bg-red-500',    cn: '极度高估' },
  insufficient:       { badge: 'bg-slate-50 text-slate-300',    text: 'text-slate-300',  bar: 'bg-slate-200',  cn: '—'        },
}

const Z_COLOR: Record<LabelEn, string> = {
  extreme_undervalue: '#1d4ed8',
  undervalue:         '#3b82f6',
  neutral:            '#64748b',
  overvalue:          '#f97316',
  extreme_overvalue:  '#ef4444',
  insufficient:       '#cbd5e1',
}

type SelectedItem =
  | { type: 'sector'; data: SectorWithIndustries }
  | { type: 'industry'; data: IndustryValuation; sectorCn: string }

function ValuationBadge({ labelEn, zScore }: { labelEn: string; zScore: number | null }) {
  const key = (labelEn || 'insufficient') as LabelEn
  const cfg = LABEL_CONFIG[key]
  const zStr = zScore !== null ? (zScore >= 0 ? '+' : '') + zScore.toFixed(2) : null
  return (
    <span className={`flex flex-col items-center px-1.5 py-0.5 rounded shrink-0 min-w-[46px] ${cfg.badge}`}>
      <span className="text-[10px] font-bold leading-tight">{cfg.cn}</span>
      {zStr && <span className="text-[9px] font-mono leading-tight opacity-70">{zStr}σ</span>}
    </span>
  )
}

function DetailPanel({ item }: { item: SelectedItem }) {
  const d = item.data
  const key = (d.label_en || 'insufficient') as LabelEn
  const zColor = Z_COLOR[key]
  const zStr = d.z_score !== null ? (d.z_score >= 0 ? '+' : '') + d.z_score.toFixed(2) : '—'
  const title = item.type === 'sector'
    ? (item.data as SectorWithIndustries).sector_cn
    : (item.data as IndustryValuation).industry_cn
  const subtitle = item.type === 'sector'
    ? (item.data as SectorWithIndustries).sector
    : `${item.sectorCn} › ${(item.data as IndustryValuation).industry}`

  const hasPE = d.hist_pe.length >= 4 && d.hist_mean !== null && d.hist_std !== null

  return (
    <div className="space-y-4 flex flex-col h-full">
      {/* 头部卡片 */}
      <div className="rounded-xl border border-slate-100 bg-gradient-to-br from-slate-50 to-white px-4 py-3">
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xl font-extrabold text-slate-900 leading-tight">{title}</span>
              <ValuationBadge labelEn={d.label_en} zScore={d.z_score} />
            </div>
            <div className="text-[11px] text-slate-400 mt-0.5 truncate">{subtitle}</div>
            <div className="flex items-center gap-4 mt-2.5 flex-wrap">
              {d.current_pe !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">当前 PE</span>
                  <span className="text-sm font-bold text-slate-800 font-mono">{d.current_pe.toFixed(2)}</span>
                </div>
              )}
              {d.hist_mean !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">5年均值</span>
                  <span className="text-sm font-bold text-slate-600 font-mono">{d.hist_mean.toFixed(2)}</span>
                </div>
              )}
              {d.hist_std !== null && (
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-400">±1σ</span>
                  <span className="text-sm font-bold text-slate-600 font-mono">{d.hist_std.toFixed(2)}</span>
                </div>
              )}
              <div className="flex flex-col">
                <span className="text-[10px] text-slate-400">数据</span>
                <span className="text-sm font-bold text-slate-500 font-mono">{d.data_quarters}Q</span>
              </div>
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-4xl font-extrabold font-mono tracking-tighter leading-none" style={{ color: zColor }}>
              {zStr}
            </div>
            <div className="text-[10px] text-slate-400 mt-1 font-medium">z-score (σ)</div>
          </div>
        </div>
      </div>

      {/* PE 走势图 */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-bold text-slate-700">近 5 年季度 PE 走势</h4>
          <span className="text-[10px] text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
            ±1σ / ±2σ 历史区间
          </span>
        </div>
        {hasPE ? (
          <SectorPEChart
            histPE={d.hist_pe as { date: string; pe: number }[]}
            mean={d.hist_mean as number}
            std={d.hist_std as number}
            currentPE={d.current_pe}
            label_en={d.label_en}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-52 rounded-xl border border-dashed border-slate-200 bg-slate-50/50">
            <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div className="text-sm text-slate-400 font-medium">暂无 PE 历史数据</div>
            <div className="text-[11px] text-slate-300 mt-1">历史数据不足 4 个季度</div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SectorValuationGrid() {
  const [gics, setGics] = useState<GICSValuationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<SelectedItem | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchGICSValuations()
      .then((res) => {
        setGics(res)
        setLoading(false)
        if (res.sectors.length > 0) {
          const first = res.sectors[0]
          setExpanded(new Set([first.sector]))
          // 默认选中第一个有数据的板块
          setSelected({ type: 'sector', data: first })
        }
      })
      .catch(() => {
        setError('行业估值数据加载失败，请重试')
        setLoading(false)
      })
  }, [])

  const toggleSector = (sector: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) next.delete(sector)
      else next.add(sector)
      return next
    })
  }

  // 顶部统计
  const stats = useMemo(() => {
    if (!gics) return { under: 0, neutral: 0, over: 0, total: 0 }
    let under = 0, neutral = 0, over = 0
    for (const s of gics.sectors) {
      const z = s.z_score
      if (z === null) continue
      if (z <= -1) under++
      else if (z >= 1) over++
      else neutral++
    }
    return { under, neutral, over, total: gics.sectors.length }
  }, [gics])

  return (
    <div className="space-y-3">
      {/* 顶部摘要条 */}
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl border border-slate-200 bg-white flex-wrap text-xs text-slate-500 shadow-sm">
        <span className="text-slate-400">
          数据截至 <span className="font-semibold text-slate-600">{gics?.as_of || '—'}</span>
        </span>
        <span className="text-slate-200">|</span>
        <span className="text-slate-400">GICS 行业 PE · 近 5 年 z-score</span>
        {gics && (
          <>
            <span className="text-slate-200">|</span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
              <span className="text-blue-600 font-medium">低估 {stats.under}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-300 inline-block" />
              <span>中性 {stats.neutral}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-orange-400 inline-block" />
              <span className="text-orange-500 font-medium">高估 {stats.over}</span>
            </span>
          </>
        )}
      </div>

      {/* 主区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-3">

        {/* ── 左侧：GICS 层级树 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden self-start">
          <div className="px-3 py-2.5 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">行业 / 子行业</div>
            <div className="text-[9px] text-slate-300 mt-0.5">点击查看 PE 走势 · ▶ 展开子行业</div>
          </div>

          <div className="px-1.5 py-1.5 max-h-[720px] overflow-y-auto">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Spinner className="w-5 h-5 text-slate-400" />
                <div className="text-xs text-slate-400">正在加载行业估值数据…</div>
                <div className="text-[10px] text-slate-300">首次约 15 秒，之后 4h 缓存</div>
              </div>
            ) : error ? (
              <div className="py-8 text-center text-sm text-red-400">{error}</div>
            ) : (
              <div className="space-y-0.5">
                {gics?.sectors.map((sec) => {
                  const isExpanded = expanded.has(sec.sector)
                  const sKey = (sec.label_en || 'insufficient') as LabelEn
                  const cfg = LABEL_CONFIG[sKey]
                  const isSectorSelected = selected?.type === 'sector' && (selected.data as SectorWithIndustries).sector === sec.sector

                  return (
                    <div key={sec.sector}>
                      {/* 板块行 */}
                      <div className="flex items-center gap-1.5">
                        {/* 展开按钮 */}
                        <button
                          type="button"
                          onClick={() => toggleSector(sec.sector)}
                          className="shrink-0 w-5 h-5 flex items-center justify-center text-slate-300 hover:text-slate-500 transition-colors"
                        >
                          <span className="text-[9px]" style={{ display: 'inline-block', transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>▶</span>
                        </button>
                        {/* 估值颜色条 */}
                        <span className={`flex-shrink-0 w-0.5 h-4 rounded-full ${cfg.bar}`} />
                        {/* 板块名称（可点击） */}
                        <button
                          type="button"
                          onClick={() => setSelected({ type: 'sector', data: sec })}
                          className={`flex-1 flex items-center gap-2 px-1.5 py-1.5 rounded-lg text-left transition-all ${
                            isSectorSelected ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-slate-50'
                          }`}
                        >
                          <span className="flex-1 text-xs font-semibold text-slate-700 truncate">{sec.sector_cn}</span>
                          <span className="text-[10px] font-mono text-slate-400 shrink-0">
                            {sec.current_pe !== null ? `PE ${sec.current_pe.toFixed(1)}` : ''}
                          </span>
                          <ValuationBadge labelEn={sec.label_en} zScore={sec.z_score} />
                        </button>
                      </div>

                      {/* 子行业列表 */}
                      {isExpanded && sec.industries.length > 0 && (
                        <div className="ml-6 mb-1 space-y-0.5 border-l-2 border-slate-100 pl-2">
                          {sec.industries.map((ind) => {
                            const iKey = (ind.label_en || 'insufficient') as LabelEn
                            const iCfg = LABEL_CONFIG[iKey]
                            const isIndSelected = selected?.type === 'industry' &&
                              (selected.data as IndustryValuation).industry === ind.industry
                            return (
                              <button
                                key={ind.industry}
                                type="button"
                                onClick={() => setSelected({ type: 'industry', data: ind, sectorCn: sec.sector_cn })}
                                className={`w-full flex items-center gap-1.5 px-2 py-1 rounded-md text-left transition-all ${
                                  isIndSelected ? 'bg-blue-50 ring-1 ring-blue-200' : 'hover:bg-slate-50'
                                }`}
                              >
                                <span className={`flex-shrink-0 w-0.5 h-3 rounded-full ${iCfg.bar}`} />
                                <span className="flex-1 text-[11px] text-slate-600 truncate">{ind.industry_cn}</span>
                                <ValuationBadge labelEn={ind.label_en} zScore={ind.z_score} />
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── 右侧：详情面板 ── */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 min-h-[520px] flex flex-col">
          {!selected ? (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-400 gap-3">
              <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="text-sm font-medium text-slate-400">点击左侧行业查看估值详情</div>
            </div>
          ) : (
            <DetailPanel item={selected} />
          )}
        </div>
      </div>

      {/* 底部说明 */}
      <p className="text-[11px] text-slate-400 px-1 leading-relaxed">
        <span className="font-medium text-slate-500">z-score</span> = (当前季度 PE − 近 5 年历史均值) ÷ 标准差。
        一级行业数据来自 FMP sector_price_earning_ratio；子行业来自 industry_price_earning_ratio。
      </p>
    </div>
  )
}
