export type PanicLevel = 'extreme_panic' | 'panic' | 'neutral' | 'calm' | 'extreme_calm'

export interface PanicLevelConfig {
  label: string
  color: string
  bgGradient: string
  badgeClass: string
}

export const PANIC_LEVEL_CONFIG: Record<PanicLevel, PanicLevelConfig> = {
  extreme_panic: {
    label: '极度恐慌',
    color: '#ef4444',
    bgGradient: 'rgba(239,68,68,0.15)',
    badgeClass: 'bg-red-100 text-red-600',
  },
  panic: {
    label: '恐慌',
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
  calm: {
    label: '平静',
    color: '#3b82f6',
    bgGradient: 'rgba(59,130,246,0.12)',
    badgeClass: 'bg-blue-100 text-blue-600',
  },
  extreme_calm: {
    label: '极度平静',
    color: '#1d4ed8',
    bgGradient: 'rgba(29,78,216,0.15)',
    badgeClass: 'bg-blue-200 text-blue-700',
  },
}

/** z-score → 0-100 恐慌指数（50=中性，>50恐慌，<50平静） */
export function zScoreToPanic(z: number | null): number {
  if (z === null) return 50
  return Math.max(0, Math.min(100, 50 + z * 20))
}

export function panicToLevel(panic: number): PanicLevel {
  if (panic >= 80) return 'extreme_panic'
  if (panic >= 60) return 'panic'
  if (panic >= 40) return 'neutral'
  if (panic >= 20) return 'calm'
  return 'extreme_calm'
}

export function getPanicColor(panic: number): string {
  return PANIC_LEVEL_CONFIG[panicToLevel(panic)].color
}

export function getPanicLevel(panic: number): PanicLevelConfig {
  return PANIC_LEVEL_CONFIG[panicToLevel(panic)]
}
