import { create } from 'zustand'
import {
  fetchSectorRegimes,
  triggerSectorStage,
  type SectorRegimePoint,
} from '@/lib/api/regime'

/**
 * 板块状态（行业级 regime）全局 store。
 *
 * 把数据与「重新计算」放到 store 而非组件里，这样：
 * - 切换 Tab 导致面板卸载时，数据与 running 状态不丢；
 * - 慢速的重新计算（POST）promise 活在 store action 中，组件卸载也不影响它，
 *   算完自动写回 store，任何已挂载的订阅者随之更新。
 */
interface SectorRegimeState {
  sectors: SectorRegimePoint[]
  tradeDate: string | null
  loading: boolean
  running: boolean
  error: string | null
  loaded: boolean
  load: (force?: boolean) => Promise<void>
  run: () => Promise<void>
}

export const useSectorRegimeStore = create<SectorRegimeState>((set, get) => ({
  sectors: [],
  tradeDate: null,
  loading: false,
  running: false,
  error: null,
  loaded: false,

  load: async (force = false) => {
    // 已加载过且非强制、且不在加载中 → 直接用缓存，避免切回 Tab 闪一下 loading
    if (get().loaded && !force) return
    if (get().loading) return
    set({ loading: true, error: null })
    try {
      const resp = await fetchSectorRegimes()
      set({ sectors: resp.sectors, tradeDate: resp.trade_date, loading: false, loaded: true })
    } catch {
      set({ error: '加载板块状态失败', loading: false })
    }
  },

  run: async () => {
    if (get().running) return // 防重复触发
    set({ running: true, error: null })
    try {
      await triggerSectorStage()
      const resp = await fetchSectorRegimes()
      set({ sectors: resp.sectors, tradeDate: resp.trade_date, running: false, loaded: true })
    } catch {
      set({ error: '重新计算失败（需登录且行情可用）', running: false })
    }
  },
}))
