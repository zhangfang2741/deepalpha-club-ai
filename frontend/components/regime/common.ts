// frontend/components/regime/common.ts
// 市场状态（regime）共享色板与标签工具。A 股约定：红=贪婪/逐利，绿=恐慌/避险。
import { REGIME_LABEL_ZH } from '@/lib/api/regime'

export const LABEL_COLOR: Record<string, string> = {
  risk_on: '#dc2626', // 逐利 红（贪婪）
  neutral: '#d97706', // 观望 橙
  risk_off: '#16a34a', // 避险 绿（恐慌）
}
export const NEUTRAL_COLOR = '#64748b'

export function labelZh(label: string | null): string {
  if (!label) return '数据不足'
  return REGIME_LABEL_ZH[label] ?? label
}

export function colorOf(label: string | null): string {
  return label ? LABEL_COLOR[label] ?? NEUTRAL_COLOR : NEUTRAL_COLOR
}
