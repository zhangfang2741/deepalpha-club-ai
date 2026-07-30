import { create } from 'zustand'
import {
  fetchSectorRegimes,
  fetchSectorChildren,
  triggerSectorStage,
  type SectorRegimePoint,
} from '@/lib/api/regime'

// 把 axios 错误翻成能区分原因的中文（登录 / 超时 / 服务端错误）
function runErrorMessage(err: unknown): string {
  const e = err as { response?: { status?: number }; code?: string }
  const status = e?.response?.status
  if (status === 401 || status === 403) return '请先登录后再重新计算'
  if (e?.code === 'ECONNABORTED') return '计算超时：板块+子行业共 39 只 ETF，同步计算较慢，建议改后台调度'
  if (status === 502 || status === 504) return '计算超时（网关 502/504）：数据量大，建议改后台调度'
  if (status && status >= 500) return `服务器错误（${status}），请稍后重试`
  if (status) return `重新计算失败（${status}）`
  return '重新计算失败：网络错误或行情不可用'
}

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
  // 下钻：当前展开的一级行业 + 其子行业缓存
  openSector: string | null
  childrenCache: Record<string, SectorRegimePoint[]>
  childrenLoading: boolean
  load: (force?: boolean) => Promise<void>
  run: () => Promise<void>
  openChildren: (sector: string) => Promise<void>
  closeChildren: () => void
}

export const useSectorRegimeStore = create<SectorRegimeState>((set, get) => ({
  sectors: [],
  tradeDate: null,
  loading: false,
  running: false,
  error: null,
  loaded: false,
  openSector: null,
  childrenCache: {},
  childrenLoading: false,

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
    } catch (err) {
      set({ error: runErrorMessage(err), running: false })
    }
  },

  openChildren: async (sector: string) => {
    set({ openSector: sector })
    if (get().childrenCache[sector]) return // 命中缓存不再拉
    set({ childrenLoading: true })
    try {
      const resp = await fetchSectorChildren(sector)
      set((s) => ({
        childrenCache: { ...s.childrenCache, [sector]: resp.children },
        childrenLoading: false,
      }))
    } catch {
      set({ childrenLoading: false })
    }
  },

  closeChildren: () => set({ openSector: null }),
}))
