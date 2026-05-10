/**
 * Fear & Greed Index 常量定义
 */

export type FearGreedRating =
  | 'Extreme Greed'
  | 'Greed'
  | 'Neutral'
  | 'Fear'
  | 'Extreme Fear'

/** 情绪等级对应的颜色 - 红色系=贪婪, 绿色系=恐惧 */
export const RATING_COLOR: Record<FearGreedRating, string> = {
  'Extreme Greed': '#ef4444',
  'Greed': '#f87171',
  'Neutral': '#ca8a04',
  'Fear': '#4ade80',
  'Extreme Fear': '#16a34a',
}

/** 情绪等级的中文标签 */
export const RATING_LABEL: Record<FearGreedRating, string> = {
  'Extreme Greed': '极度贪婪',
  'Greed': '贪婪',
  'Neutral': '中性',
  'Fear': '恐惧',
  'Extreme Fear': '极度恐惧',
}

/** 获取情绪等级颜色，未知等级返回默认蓝色 */
export function getRatingColor(rating: string): string {
  return RATING_COLOR[rating as FearGreedRating] ?? '#3b82f6'
}

/** 获取情绪等级中文标签，未知等级返回原始值 */
export function getRatingLabel(rating: string): string {
  return RATING_LABEL[rating as FearGreedRating] ?? rating
}
