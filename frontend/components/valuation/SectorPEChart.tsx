'use client'

import { useMemo, useRef, useState } from 'react'
import type { SectorPERecord } from '@/lib/api/valuation'

interface Props {
  histPE: SectorPERecord[]
  mean: number
  std: number
  currentPE: number | null
  label?: string
  label_en?: string
}

const PAD = { top: 24, right: 92, bottom: 44, left: 56 }
const W = 780
const H = 340

type LabelEn = 'extreme_undervalue' | 'undervalue' | 'neutral' | 'overvalue' | 'extreme_overvalue' | 'insufficient'

const ZONE_COLORS: Record<LabelEn, string> = {
  extreme_undervalue: '#1d4ed8',
  undervalue:         '#3b82f6',
  neutral:            '#64748b',
  overvalue:          '#f97316',
  extreme_overvalue:  '#ef4444',
  insufficient:       '#94a3b8',
}

function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return ''
  if (pts.length === 1) return `M${pts[0].x},${pts[0].y}`
  const d: string[] = [`M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`]
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(i + 2, pts.length - 1)]
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d.push(`C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`)
  }
  return d.join(' ')
}

export default function SectorPEChart({ histPE, mean, std, currentPE, label_en }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<{ idx: number; x: number; y: number } | null>(null)

  const { yMin, yMax, pts, sigmaY, yearMarkers, gradId, curveColor } = useMemo(() => {
    const allPEs = [...histPE.map((p) => p.pe)]
    if (currentPE !== null) allPEs.push(currentPE)
    if (allPEs.length === 0)
      return { yMin: 0, yMax: 100, pts: [], sigmaY: {}, yearMarkers: [], gradId: 'g0', curveColor: '#0f172a' }

    const lo = Math.min(...allPEs, mean - 2.8 * std)
    const hi = Math.max(...allPEs, mean + 2.8 * std)
    const pad = (hi - lo) * 0.07
    const yMin = lo - pad
    const yMax = hi + pad

    const innerW = W - PAD.left - PAD.right
    const innerH = H - PAD.top - PAD.bottom

    const xScale = (i: number) => PAD.left + (i / Math.max(histPE.length - 1, 1)) * innerW
    const yScale = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * innerH

    const pts = histPE.map((p, i) => ({ x: xScale(i), y: yScale(p.pe), date: p.date, pe: p.pe }))

    const sigmaVals = { p2: mean + 2 * std, p1: mean + std, mu: mean, m1: mean - std, m2: mean - 2 * std }
    const sigmaY = Object.fromEntries(Object.entries(sigmaVals).map(([k, v]) => [k, yScale(v)]))

    // 年份分界标记：找每年第一个数据点
    const yearMarkers: { x: number; year: string; isFirst: boolean }[] = []
    let lastYear = ''
    histPE.forEach((p, i) => {
      const yr = p.date.slice(0, 4)
      if (yr !== lastYear) {
        yearMarkers.push({ x: xScale(i), year: yr, isFirst: i === 0 })
        lastYear = yr
      }
    })

    const key = (label_en || 'insufficient') as LabelEn
    const curveColor = ZONE_COLORS[key] ?? '#0f172a'
    const gradId = `grad-${key}`

    return { yMin, yMax, pts, sigmaY: sigmaY as Record<string, number>, yearMarkers, gradId, curveColor }
  }, [histPE, mean, std, currentPE, label_en])

  const innerL = PAD.left
  const innerR = W - PAD.right
  const innerW = innerR - innerL
  const topY = PAD.top
  const botY = H - PAD.bottom

  const yScale = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (H - PAD.top - PAD.bottom)

  const zones = [
    { y1: topY,                                                           y2: Math.max(Math.min(sigmaY.p2 ?? topY, botY), topY), fill: 'rgba(239,68,68,0.10)'  },
    { y1: Math.max(Math.min(sigmaY.p2 ?? topY, botY), topY),             y2: Math.max(Math.min(sigmaY.p1 ?? topY, botY), topY), fill: 'rgba(249,115,22,0.10)' },
    { y1: Math.max(Math.min(sigmaY.p1 ?? topY, botY), topY),             y2: Math.min(Math.max(sigmaY.m1 ?? botY, topY), botY), fill: 'rgba(241,245,249,0.70)' },
    { y1: Math.min(Math.max(sigmaY.m1 ?? botY, topY), botY),             y2: Math.min(Math.max(sigmaY.m2 ?? botY, topY), botY), fill: 'rgba(59,130,246,0.10)'  },
    { y1: Math.min(Math.max(sigmaY.m2 ?? botY, topY), botY),             y2: botY,                                               fill: 'rgba(29,78,216,0.14)'  },
  ]

  const curvePath = smoothPath(pts)
  const areaPath = pts.length > 1
    ? `${curvePath} L${pts[pts.length - 1].x.toFixed(1)},${botY} L${pts[0].x.toFixed(1)},${botY} Z`
    : ''

  const hoverPt = hover !== null ? pts[hover.idx] : null
  const currentY = currentPE !== null ? yScale(currentPE) : null
  const currentX = pts.length > 0 ? pts[pts.length - 1].x : innerR

  const sigmaLines = [
    { key: 'p2', label: '+2σ', val: mean + 2 * std, color: '#ef4444' },
    { key: 'p1', label: '+1σ', val: mean + std,     color: '#f97316' },
    { key: 'mu', label: 'μ',   val: mean,            color: '#64748b' },
    { key: 'm1', label: '-1σ', val: mean - std,     color: '#3b82f6' },
    { key: 'm2', label: '-2σ', val: mean - 2 * std, color: '#1d4ed8' },
  ]

  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const v = yMin + (i / 4) * (yMax - yMin)
    return { y: yScale(v), label: v.toFixed(1) }
  })

  // 数据时间范围
  const dateRange = histPE.length >= 2
    ? `${histPE[0].date.slice(0, 7)} — ${histPE[histPE.length - 1].date.slice(0, 7)}  ·  ${histPE.length} 个季度`
    : ''

  return (
    <div className="relative w-full select-none">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={curveColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={curveColor} stopOpacity="0.02" />
          </linearGradient>
          <clipPath id="chart-clip">
            <rect x={innerL} y={topY} width={innerW} height={botY - topY} />
          </clipPath>
        </defs>

        {/* Zone backgrounds */}
        {zones.map((z, i) => (
          <rect
            key={i}
            x={innerL}
            y={Math.min(z.y1, z.y2)}
            width={innerW}
            height={Math.max(Math.abs(z.y2 - z.y1), 0)}
            fill={z.fill}
          />
        ))}

        {/* 年份分隔虚线 */}
        {yearMarkers.filter(m => !m.isFirst).map((m) => (
          <line
            key={`yr-${m.year}`}
            x1={m.x} x2={m.x}
            y1={topY} y2={botY}
            stroke="rgba(148,163,184,0.25)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        ))}

        {/* Y轴网格线 */}
        {yTicks.map((t, i) => (
          <line key={i} x1={innerL} x2={innerR} y1={t.y} y2={t.y}
            stroke="rgba(148,163,184,0.15)" strokeWidth={1} />
        ))}

        {/* σ 参考线 */}
        {sigmaLines.map((sl) => {
          const y = sigmaY[sl.key]
          if (y === undefined || y < topY - 5 || y > botY + 5) return null
          return (
            <g key={sl.key}>
              <line x1={innerL} x2={innerR} y1={y} y2={y}
                stroke={sl.color}
                strokeOpacity={sl.key === 'mu' ? 0.65 : 0.4}
                strokeWidth={sl.key === 'mu' ? 1.5 : 1}
                strokeDasharray={sl.key === 'mu' ? '0' : '5 4'} />
              <text x={innerR + 6} y={y + 4} fontSize="10.5" fontFamily="ui-monospace,monospace" fill={sl.color} fontWeight="700">
                {sl.label}
              </text>
              <text x={innerR + 6} y={y + 16} fontSize="9" fontFamily="ui-monospace,monospace" fill={sl.color} opacity="0.7">
                {sl.val.toFixed(1)}
              </text>
            </g>
          )
        })}

        {/* 面积填充 */}
        {areaPath && <path d={areaPath} fill={`url(#${gradId})`} clipPath="url(#chart-clip)" />}

        {/* 曲线 */}
        {curvePath && (
          <path d={curvePath} fill="none" stroke={curveColor} strokeWidth={2.4}
            strokeLinejoin="round" strokeLinecap="round" clipPath="url(#chart-clip)" />
        )}

        {/* 数据点 */}
        {pts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y}
            r={i === hover?.idx ? 5.5 : 3.5}
            fill={i === hover?.idx ? curveColor : 'white'}
            stroke={curveColor} strokeWidth={2}
            style={{ transition: 'r 0.1s' }} />
        ))}

        {/* 当前值高亮 */}
        {currentY !== null && (
          <g>
            <circle cx={currentX} cy={currentY} r={8} fill={curveColor} opacity="0.12" />
            <circle cx={currentX} cy={currentY} r={5} fill={curveColor} stroke="white" strokeWidth={2} />
          </g>
        )}

        {/* 图表边框 */}
        <rect x={innerL} y={topY} width={innerW} height={botY - topY}
          fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth={1} />

        {/* Y轴标签 */}
        {yTicks.map((t, i) => (
          <text key={i} x={innerL - 8} y={t.y + 4} textAnchor="end"
            fontSize="10" fontFamily="ui-monospace,monospace" fill="#94a3b8">
            {t.label}
          </text>
        ))}

        {/* X轴年份标签 */}
        {yearMarkers.map((m) => (
          <text key={`label-${m.year}`} x={m.x} y={botY + 18} textAnchor="middle"
            fontSize="11" fontFamily="ui-monospace,monospace" fill="#64748b" fontWeight="600">
            {m.year}
          </text>
        ))}

        {/* Hover 十字线 */}
        {hoverPt && (
          <line x1={hoverPt.x} x2={hoverPt.x} y1={topY} y2={botY}
            stroke={curveColor} strokeWidth={1} strokeDasharray="3 3" opacity="0.5" />
        )}

        {/* Hover 命中区 */}
        {pts.map((p, i) => (
          <rect key={`hit-${i}`} x={p.x - 18} y={topY} width={36} height={botY - topY}
            fill="transparent"
            onMouseEnter={() => setHover({ idx: i, x: p.x, y: p.y })} />
        ))}
      </svg>

      {/* 时间范围标签 */}
      {dateRange && (
        <div className="text-center text-[10px] text-slate-400 font-mono -mt-1 mb-1">{dateRange}</div>
      )}

      {/* Hover 浮层 */}
      {hoverPt && (
        <div className="absolute pointer-events-none z-20" style={{
          left: `${(hoverPt.x / W) * 100}%`,
          top: `${(hoverPt.y / H) * 100}%`,
          transform: 'translate(-50%, -140%)',
        }}>
          <div className="bg-white border border-slate-200 rounded-xl shadow-xl px-3.5 py-2.5 text-xs whitespace-nowrap">
            <div className="text-slate-400 mb-1 font-medium">{pts[hover!.idx]?.date}</div>
            <div className="font-bold text-slate-900 font-mono text-sm">PE {pts[hover!.idx]?.pe.toFixed(2)}</div>
          </div>
        </div>
      )}

      {/* 图例 + 区间说明 */}
      <div className="flex items-center gap-3 mt-2 px-1 flex-wrap">
        {[
          { color: 'rgba(29,78,216,0.45)',  label: '极度低估 ≤-2σ' },
          { color: 'rgba(59,130,246,0.45)', label: '低估 -2~-1σ' },
          { color: 'rgba(203,213,225,0.5)', label: '中性 ±1σ', border: true },
          { color: 'rgba(249,115,22,0.45)', label: '高估 +1~+2σ' },
          { color: 'rgba(239,68,68,0.45)',  label: '极度高估 ≥+2σ' },
        ].map((z) => (
          <span key={z.label} className="flex items-center gap-1 text-[10px] text-slate-400">
            <span className={`inline-block w-3 h-3 rounded-sm flex-shrink-0 ${z.border ? 'border border-slate-300' : ''}`}
              style={{ background: z.color }} />
            {z.label}
          </span>
        ))}
      </div>
    </div>
  )
}
