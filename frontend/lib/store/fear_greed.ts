import { create } from 'zustand'
import { fetchFearGreed, FearGreedResponse } from '@/lib/api/fear_greed'

interface FearGreedState {
  data: FearGreedResponse | null
  loading: boolean
  error: string | null
  startDate: string | null
  endDate: string | null
  fetchData: (startDate?: string, endDate?: string) => Promise<void>
}

export const useFearGreedStore = create<FearGreedState>((set) => ({
  data: null,
  loading: false,
  error: null,
  startDate: null,
  endDate: null,
  fetchData: async (startDate?: string, endDate?: string) => {
    set({ loading: true, error: null, startDate: startDate ?? null, endDate: endDate ?? null })
    try {
      const data = await fetchFearGreed(startDate, endDate)
      set({ data, loading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : '数据加载失败'
      set({ error: message, loading: false })
    }
  },
}))
