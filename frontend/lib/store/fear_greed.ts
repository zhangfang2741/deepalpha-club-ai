import { create } from 'zustand'
import { fetchFearGreed, FearGreedResponse } from '@/lib/api/fear_greed'

interface FearGreedState {
  data: FearGreedResponse | null
  loading: boolean
  error: string | null
  fetchData: () => Promise<void>
}

export const useFearGreedStore = create<FearGreedState>((set) => ({
  data: null,
  loading: false,
  error: null,
  fetchData: async () => {
    set({ loading: true, error: null })
    try {
      const data = await fetchFearGreed()
      set({ data, loading: false })
    } catch (err) {
      const message = err instanceof Error ? err.message : '数据加载失败'
      set({ error: message, loading: false })
    }
  },
}))
