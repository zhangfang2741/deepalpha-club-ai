// frontend/lib/store/etf.ts
import { create } from 'zustand'
import type { Granularity } from '@/lib/api/etf'

interface ETFState {
  granularity: Granularity
  days: number
  setGranularity: (g: Granularity) => void
}

export const useETFStore = create<ETFState>((set) => ({
  granularity: 'day',
  days: 30,
  setGranularity: (granularity) => set({ granularity }),
}))
