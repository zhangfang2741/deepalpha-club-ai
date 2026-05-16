'use client'

import { useMemo, useState } from 'react'
import type { SectorPERecord } from '@/lib/api/valuation'

interface Props {
  histPE: SectorPERecord[]
  mean: number
  std: number
  currentPE: number | null
  currentDate: string
}

const PADDING = { top: 14, right: 80, bottom: 28, left: 44 }
const WIDTH = 720
const HEIGHT = 320

const ZONE_FILL = {
  extremeLow: 'rgba(29,78,216,0.18)',
  low: 'rgba(96,165,250,0.22)',
  neutral: 'rgba(241,245,249,0.65)',
  high: 'rgba(251,146,60,0.22)',
  extremeHigh: 'rgba(220,38,38,0.20)',
}

export default function SectorPEChart({ histPE, mean, std, currentPE, currentDate }: Props) {
  const [hover, setHover] = useState<{ x: number; y: number; date: string; pe: number } | null>(null)

  const { yMin, yMax, points, sigmaLines, xLabels } = useMemo(() => {
    const allPEs = histPE.map((p) => p.pe)
    if (currentPE !== null) allPEs.push(currentPE)
    const dataMin = Math.min(...allPEs, mean - 2.5 * std)
    const dataMax = Math.max(...allPEs, mean + 2.5 * std)
    const range = dataMax - dataMin
    const pad = range * 0.08
    const yMin = dataMin - pad
    const yMax = dataMax + pad

    const xScale = (i: number) =>
      PADDING.left + (i / Math.max(histPE.length - 1, 1)) * (WIDTH - PADDING.left - PADDING.right)
    const yScale = (v: number) =>
      PADDING.top + (1 - (v - yMin) / (yMax - yMin)) * (HEIGHT - PADDING.top - PADDING.bottom)

    const points = histPE.map((p, i) => ({
      x: xScale(i),
      y: yScale(p.pe),
      date: p.date,
      pe: p.pe,
    }))

    const sigmaLines = [
      { label: '+2σ', value: mean + 2 * std, color: '#dc2626' },
      { label: '+1σ', value: mean + std, color: '#f97316' },
      { label: 'μ', value: mean, color: '#64748b' },
      { label: '-1σ', value: mean - std, color: '#3b82f6' },
      { label: '-2σ', value: mean - 2 * std, color: '#1d4ed8' },
    ].map((l) => ({ ...l, y: yScale(l.value) }))

    // 6 等距 x 轴标签
    const labelIdxs = histPE.length <= 6
      ? histPE.map((_, i) => i)
      : Array.from({ length: 6 }, (_, k) => Math.round((k * (histPE.length - 1)) / 5))
    const xLabels = labelIdxs.map((i) => ({
      x: xScale(i),
      text: histPE[i]?.date?.slice(0, 7) ?? '',
    }))

    return { yMin, yMax, points, sigmaLines, xLabels }
  }, [histPE, mean, std, currentPE])

  const yScale = (v: number) =>
    PADDING.top + (1 - (v - yMin) / (yMax - yMin)) * (HEIGHT - PADDING.top - PADDING.bottom)

  const innerLeft = PADDING.left
  const innerRight = WIDTH - PADDING.right
  const innerWidth = innerRight - innerLeft
  const topY = PADDING.top
  const bottomY = HEIGHT - PADDING.bottom

  const zones = [
    { y1: topY, y2: Math.max(yScale(mean + 2 * std), topY), fill: ZONE_FILL.extremeHigh },
    { y1: Math.max(yScale(mean + 2 * std), topY), y2: yScale(mean + std), fill: ZONE_FILL.high },
    { y1: yScale(mean + std), y2: yScale(mean - std), fill: ZONE_FILL.neutral },
    { y1: yScale(mean - std), y2: Math.min(yScale(mean - 2 * std), bottomY), fill: ZONE_FILL.low },
    { y1: Math.min(yScale(mean - 2 * std), bottomY), y2: bottomY, fill: ZONE_FILL.extremeHigh.replace('220,38,38', '29,78,216') },
  ]

  const pathD = points.length > 0
    ? 'M' + points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' L')
    : ''

  const currentX = points.length > 0 ? points[points.length - 1].x : innerRight
  const currentY = currentPE !== null ? yScale(currentPE) : null

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
        onMouseLeave={() => setHover(null)}
      >
        {/* 区块背景 */}
        {zones.map((z, idx) => (
          <rect
            key={idx}
            x={innerLeft}
            y={Math.min(z.y1, z.y2)}
            width={innerWidth}
            height={Math.abs(z.y2 - z.y1)}
            fill={z.fill}
          />
        ))}

        {/* sigma 水平线（虚线） */}
        {sigmaLines.map((l) => (
          <g key={l.label}>
            <line
              x1={innerLeft}
              x2={innerRight}
              y1={l.y}
              y2={l.y}
              stroke={l.color}
              strokeOpacity={0.55}
              strokeWidth={1}
              strokeDasharray={l.label === 'μ' ? '0' : '4 4'}
            />
            <text
              x={innerRight + 6}
              y={l.y + 3}
              fontSize="10"
              fontFamily="ui-monospace, monospace"
              fill={l.color}
              fontWeight="600"
            >
              {l.label} {l.value.toFixed(1)}
            </text>
          </g>
        ))}

        {/* 边框 */}
        <rect
          x={innerLeft}
          y={topY}
          width={innerWidth}
          height={bottomY - topY}
          fill="none"
          stroke="rgba(148,163,184,0.4)"
          strokeWidth={1}
        />

        {/* PE 折线 */}
        <path
          d={pathD}
          fill="none"
          stroke="#0f172a"
          strokeWidth={1.8}
          strokeLinejoin="round"
        />

        {/* 数据点 */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={3}
            fill="#0f172a"
            stroke="white"
            strokeWidth={1}
          />
        ))}

        {/* 当前点强调 */}
        {currentY !== null && (
          <circle cx={currentX} cy={currentY} r={6} fill="#0ea5e9" stroke="white" strokeWidth={2} />
        )}

        {/* X 轴标签 */}
        {xLabels.map((l, i) => (
          <text
            key={i}
            x={l.x}
            y={bottomY + 16}
            fontSize="10"
            textAnchor="middle"
            fill="#64748b"
            fontFamily="ui-monospace, monospace"
          >
            {l.text}
          </text>
        ))}

        {/* 鼠标交互区 */}
        {points.map((p, i) => (
          <rect
            key={`hit-${i}`}
            x={p.x - 14}
            y={topY}
            width={28}
            height={bottomY - topY}
            fill="transparent"
            onMouseEnter={() => setHover({ x: p.x, y: p.y, date: p.date, pe: p.pe })}
          />
        ))}

        {/* hover 垂直线 */}
        {hover && (
          <line
            x1={hover.x}
            x2={hover.x}
            y1={topY}
            y2={bottomY}
            stroke="#0ea5e9"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
      </svg>

      {/* hover tooltip */}
      {hover && (
        <div
          className="absolute pointer-events-none bg-white/95 backdrop-blur-sm border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs z-10"
          style={{
            left: `${(hover.x / WIDTH) * 100}%`,
            top: `${(hover.y / HEIGHT) * 100}%`,
            transform: 'translate(-50%, -120%)',
          }}
        >
          <div className="text-gray-500">{hover.date}</div>
          <div className="font-bold text-slate-900 font-mono">PE {hover.pe.toFixed(2)}</div>
        </div>
      )}

      {/* 当前 PE 标注 */}
      {currentPE !== null && (
        <div className="absolute top-2 left-12 text-xs text-slate-500">
          <span>当前 PE </span>
          <span className="font-bold text-slate-900 font-mono">{currentPE.toFixed(2)}</span>
          {currentDate && <span className="ml-2 text-slate-400">{currentDate}</span>}
        </div>
      )}
    </div>
  )
}
