'use client'
import { useEffect, useState } from 'react'
import { useSkillsStore } from '@/lib/store/skills'
import { getMine, deleteSkill } from '@/lib/api/skills'
import { FactorCard } from './FactorCard'

export function MineView() {
  const [skills, setSkills] = useState<Array<{ id: string; title: string; description: string; category: string; default_symbol: string; pin_priority: number | null }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { openDetail } = useSkillsStore()

  const load = () => {
    setLoading(true)
    getMine()
      .then((res) => setSkills(res.skills || []))
      .catch(() => setError('加载失败'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('确定删除这个因子？')) return
    try {
      await deleteSkill(id)
      setSkills((prev) => prev.filter((s) => s.id !== id))
    } catch {
      alert('删除失败')
    }
  }

  if (loading) return <div className="text-center py-20 text-gray-400">加载中...</div>
  if (error) return <div className="text-center py-20 text-red-400">{error}</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">我的因子</h2>
        <span className="text-sm text-gray-400">{skills.length} 个</span>
      </div>

      {skills.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-gray-400 text-lg">还没有保存的因子</p>
          <p className="text-sm text-gray-300 mt-1">去「案例馆」选择一个案例，或「新建」你自己的因子</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {skills.map((s) => (
            <div key={s.id} className="relative">
              <FactorCard
                id={s.id}
                title={s.title}
                description={s.description}
                category={s.category}
                default_symbol={s.default_symbol}
                pin_priority={s.pin_priority}
                onClick={() => openDetail(s.id)}
              />
              <button
                onClick={(e) => handleDelete(e, s.id)}
                className="absolute top-3 right-3 text-gray-300 hover:text-red-400 transition-colors"
                title="删除"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}