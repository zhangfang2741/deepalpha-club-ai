// frontend/lib/store/etf.ts
import { create } from 'zustand'
import type { Granularity } from '@/lib/api/etf'

// 每种粒度对应的交易日数量，使后端聚合后恰好约 30 个数据点
const DAYS_BY_GRANULARITY: Record<Granularity, number> = {
  day: 30,
  week: 150,  // 30 周 × 5 交易日
  month: 630, // 30 月 × 21 交易日
}

interface ETFState {
  granularity: Granularity
  days: number
  setGranularity: (g: Granularity) => void
}

export const useETFStore = create<ETFState>((set) => ({
  granularity: 'day',
  days: DAYS_BY_GRANULARITY['day'],
  setGranularity: (granularity) => set({ granularity, days: DAYS_BY_GRANULARITY[granularity] }),
}))
