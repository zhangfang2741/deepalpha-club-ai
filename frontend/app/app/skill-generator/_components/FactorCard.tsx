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

const CATEGORY_COLORS: Record<string, string> = {
  momentum: 'bg-orange-50 text-orange-600',
  reversal: 'bg-blue-50 text-blue-600',
  volatility: 'bg-purple-50 text-purple-600',
  volume: 'bg-green-50 text-green-600',
  sentiment: 'bg-red-50 text-red-600',
  technical: 'bg-gray-50 text-gray-600',
}

export function FactorCard({ id, title, description, category, default_symbol, pin_priority, onClick }: FactorCardProps) {
  const isPinned = pin_priority != null && pin_priority <= 2

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md hover:border-gray-300 transition-all duration-200 group"
    >
      {isPinned && (
        <span className="inline-block text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full mb-2">
          ⭐ 精选
        </span>
      )}
      <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">{title}</h3>
      <p className="text-sm text-gray-500 mt-1 line-clamp-2">{description}</p>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{default_symbol}</span>
        <span className={`text-xs px-2 py-0.5 rounded ${CATEGORY_COLORS[category] || 'bg-gray-50 text-gray-600'}`}>
          {CATEGORY_LABELS[category] || category}
        </span>
      </div>
    </button>
  )
}