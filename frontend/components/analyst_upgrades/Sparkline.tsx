'use client'

interface Props {
  values: number[]   // 按时间顺序，如 [allTime, year, quarter, month]
  width?: number
  height?: number
  color?: string
}

export default function Sparkline({ values, width = 120, height = 36, color = '#3b82f6' }: Props) {
  const valid = values.filter((v) => v > 0)
  if (valid.length < 2) return <span className="text-gray-300 text-xs">—</span>

  const min = Math.min(...valid)
  const max = Math.max(...valid)
  const range = max - min || 1
  const pad = 3

  const points = valid.map((v, i) => {
    const x = pad + (i / (valid.length - 1)) * (width - pad * 2)
    const y = height - pad - ((v - min) / range) * (height - pad * 2)
    return `${x},${y}`
  })

  const lastX = pad + ((valid.length - 1) / (valid.length - 1)) * (width - pad * 2)
  const lastY = height - pad - ((valid[valid.length - 1] - min) / range) * (height - pad * 2)

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={2.5} fill={color} />
    </svg>
  )
}
