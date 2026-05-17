'use client'
import { useSkillsStore } from '@/lib/store/skills'

interface FactorCardProps {
  id: string
  title: string
  description: string
  category: string
  default_symbol: string
  pin_priority: number | null
  onClick: () => void
}

const CATEGORY_LABELS: Record<string, string> = {
  momentum: '动量',
  reversal: '均值回归',
  volatility: '波动率',
  volume: '量价',
  sentiment: '情绪',
  technical: '技术指标',
}

export function FactorCard({ id, title, description, category, default_symbol, pin_priority, onClick }: FactorCardProps) {
  const isPinned = pin_priority === 1

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md hover:border-gray-300 transition-all duration-200 group"
    >
      {isPinned && (
        <span className="inline-block text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full mb-2">
          ⭐ 精选
        </span>
      )}
      <h3 className="font-semibold text-gray-900 group-hover:text-primary transition-colors">{title}</h3>
      <p className="text-sm text-gray-500 mt-1 line-clamp-2">{description}</p>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-gray-400 font-mono">{default_symbol}</span>
        <span className="text-xs text-gray-400 bg-gray-50 px-2 py-0.5 rounded">
          {CATEGORY_LABELS[category] || category}
        </span>
      </div>
    </button>
  )
}