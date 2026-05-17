'use client'
import { useEffect, useState } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { getGallery } from '@/lib/api/skills'
import { FactorCard } from './FactorCard'

interface GalleryData {
  hero: { id: string; title: string; description: string; category: string; default_symbol: string; pin_priority: number | null; [key: string]: unknown } | null
  cases: Array<{ id: string; title: string; description: string; category: string; default_symbol: string; pin_priority: number | null; [key: string]: unknown }>
}

export function GalleryView() {
  const [data, setData] = useState<GalleryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { openDetail } = useSkillsStore()

  useEffect(() => {
    getGallery()
      .then(setData)
      .catch(() => setError('加载失败，请刷新重试'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-20 text-gray-400">加载中...</div>
  if (error) return <div className="text-center py-20 text-red-400">{error}</div>
  if (!data) return null

  return (
    <div className="space-y-8">
      {/* Hero */}
      {data.hero && (
        <button
          onClick={() => openDetail(data.hero!.id)}
          className="w-full bg-white border border-gray-200 rounded-2xl p-6 hover:shadow-lg hover:border-blue-200 transition-all text-left group"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <span className="inline-block text-xs font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full mb-3">
                ⭐ 今日精选
              </span>
              <h2 className="text-2xl font-bold text-gray-900 group-hover:text-blue-600 transition-colors">
                {data.hero.title}
              </h2>
              <p className="text-gray-500 mt-2 text-base">{data.hero.description}</p>
              <div className="flex items-center gap-3 mt-4">
                <span className="text-sm font-mono text-gray-400">{data.hero.default_symbol}</span>
                <span className="text-xs text-gray-300">|</span>
                <span className="text-xs text-gray-400">点击查看详情 →</span>
              </div>
            </div>
            <div className="text-6xl opacity-20 select-none">📊</div>
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