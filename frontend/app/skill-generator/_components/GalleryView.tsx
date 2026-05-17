'use client'
import { useEffect, useState } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { getGallery } from '@/lib/api/skills'
import { FactorCard } from './FactorCard'

const CATEGORY_LABELS: Record<string, string> = {
  momentum: '动量',
  reversal: '均值回归',
  volatility: '波动率',
  volume: '量价',
  sentiment: '情绪',
  technical: '技术指标',
}

interface GalleryData {
  hero: {
    id: string
    title: string
    description: string
    category: string
    default_symbol: string
    pin_priority: number | null
    created_at: string
  } | null
  cases: Array<{
    id: string
    title: string
    description: string
    category: string
    default_symbol: string
    pin_priority: number | null
    created_at: string
  }>
}

export function GalleryView() {
  const [data, setData] = useState<GalleryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { openDetail } = useSkillsStore()

  useEffect(() => {
    getGallery()
      .then((res: GalleryData) => {
        console.log('[Gallery] loaded:', res)
        setData(res)
      })
      .catch((err) => {
        console.error('[Gallery] error:', err)
        setError(String(err))
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-gray-400">加载案例馆...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-2">
        <p className="text-red-400">加载失败</p>
        <p className="text-xs text-gray-400">{error}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-20 text-gray-400">
        <p className="text-lg">暂无数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Hero */}
      {data.hero && (
        <button
          onClick={() => openDetail(data.hero!.id)}
          className="w-full bg-gradient-to-br from-blue-50 to-white border border-blue-200 rounded-2xl p-6 hover:shadow-lg hover:border-blue-300 transition-all text-left group"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <span className="inline-block text-xs font-semibold text-blue-600 bg-blue-100 px-2.5 py-0.5 rounded-full mb-3">
                ⭐ 今日精选
              </span>
              <h2 className="text-2xl font-bold text-gray-900 group-hover:text-blue-600 transition-colors">
                {data.hero.title}
              </h2>
              <p className="text-gray-500 mt-2 text-base">{data.hero.description}</p>
              <div className="flex items-center gap-3 mt-4">
                <span className="text-xs font-mono text-blue-500 bg-blue-50 px-2 py-0.5 rounded">{data.hero.default_symbol}</span>
                <span className="text-xs text-gray-400">{CATEGORY_LABELS[data.hero.category] || data.hero.category}</span>
              </div>
            </div>
            <div className="text-5xl opacity-30 select-none">📊</div>
          </div>
        </button>
      )}

      {/* 案例网格 */}
      {data.cases.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">更多案例</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.cases.map((c) => (
              <FactorCard
                key={c.id}
                id={c.id}
                title={c.title}
                description={c.description}
                category={c.category}
                default_symbol={c.default_symbol}
                pin_priority={c.pin_priority}
                onClick={() => openDetail(c.id)}
              />
            ))}
          </div>
        </div>
      )}

      {data.cases.length === 0 && !data.hero && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg">暂无案例</p>
          <p className="text-sm mt-1">试试「新建」创建你的第一个因子</p>
        </div>
      )}
    </div>
  )
}