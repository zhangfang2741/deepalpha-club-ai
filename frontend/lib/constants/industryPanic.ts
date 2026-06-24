export type RsiLevel = 'oversold' | 'weak' | 'neutral' | 'strong' | 'overbought'

export interface RsiLevelConfig {
  label: string
  color: string
  bgGradient: string
  badgeClass: string
}

export const RSI_LEVEL_CONFIG: Record<RsiLevel, RsiLevelConfig> = {
  oversold: {
    label: '超卖',
    color: '#ef4444',
    bgGradient: 'rgba(239,68,68,0.15)',
    badgeClass: 'bg-red-100 text-red-600',
  },
  weak: {
    label: '偏弱',
    color: '#f97316',
    bgGradient: 'rgba(249,115,22,0.12)',
    badgeClass: 'bg-orange-100 text-orange-600',
  },
  neutral: {
    label: '中性',
    color: '#ca8a04',
    bgGradient: 'rgba(202,138,4,0.10)',
    badgeClass: 'bg-yellow-100 text-yellow-700',
  },
  strong: {
    label: '偏强',
    color: '#3b82f6',
    bgGradient: 'rgba(59,130,246,0.12)',
    badgeClass: 'bg-blue-100 text-blue-600',
  },
  overbought: {
    label: '超买',
    color: '#1d4ed8',
    bgGradient: 'rgba(29,78,216,0.15)',
    badgeClass: 'bg-blue-200 text-blue-700',
  },
}

export function rsiToLevel(rsi: number): RsiLevel {
  if (rsi < 30) return 'oversold'
  if (rsi < 45) return 'weak'
  if (rsi < 55) return 'neutral'
  if (rsi < 70) return 'strong'
  return 'overbought'
}

export function getRsiColor(rsi: number): string {
  return RSI_LEVEL_CONFIG[rsiToLevel(rsi)].color
}

export function getRsiLevel(rsi: number): RsiLevelConfig {
  return RSI_LEVEL_CONFIG[rsiToLevel(rsi)]
}
