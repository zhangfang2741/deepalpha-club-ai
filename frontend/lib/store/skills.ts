import { create } from 'zustand'

interface FactorSkillBrief {
  id: string
  title: string
  description: string
  category: string
  default_symbol: string
  is_public: boolean
  pin_priority: number | null
  created_at: string
}

interface SkillDetail extends FactorSkillBrief {
  code: string
  default_start_date: string
  default_end_date: string
  default_freq: string
  snapshot: Record<string, unknown>
  narrative: Record<string, unknown> | null
  owner_id: number | null
}

type Tab = 'gallery' | 'mine' | 'new'

interface SkillsStore {
  activeTab: Tab
  selectedSkillId: string | null
  detailSkill: SkillDetail | null
  detailLoading: boolean
  setActiveTab: (tab: Tab) => void
  openDetail: (skillId: string) => Promise<void>
  closeDetail: () => void
}

export const useSkillsStore = create<SkillsStore>((set) => ({
  activeTab: 'gallery',
  selectedSkillId: null,
  detailSkill: null,
  detailLoading: false,
  setActiveTab: (tab) => set({ activeTab: tab, selectedSkillId: null, detailSkill: null }),
  openDetail: async (skillId: string) => {
    set({ selectedSkillId: skillId, detailLoading: true })
    try {
      const { getSkillDetail } = await import('@/lib/api/skills')
      const skill = await getSkillDetail(skillId)
      set({ detailSkill: skill, detailLoading: false })
    } catch {
      set({ detailLoading: false })
    }
  },
  closeDetail: () => set({ selectedSkillId: null, detailSkill: null }),
}))