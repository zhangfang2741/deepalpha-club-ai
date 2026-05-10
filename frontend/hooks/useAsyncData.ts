import { useState, useEffect, useCallback } from 'react'

interface UseAsyncDataOptions<T> {
  /** 初始数据 */
  initialData?: T
  /** 是否立即执行 */
  immediate?: boolean
  /** 依赖项数组，变化时重新获取 */
  deps?: unknown[]
}

interface UseAsyncDataReturn<T> {
  /** 数据 */
  data: T | null
  /** 是否加载中 */
  loading: boolean
  /** 错误信息 */
  error: string | null
  /** 手动触发获取 */
  refetch: () => Promise<void>
  /** 重置状态 */
  reset: () => void
}

/**
 * 通用异步数据获取 Hook
 *
 * @example
 * ```tsx
 * const { data, loading, error, refetch } = useAsyncData(
 *   () => fetchETFHeatmap({ granularity: 'day', days: 5 }),
 *   { immediate: true, deps: [granularity] }
 * )
 * ```
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  options: UseAsyncDataOptions<T> = {}
): UseAsyncDataReturn<T> {
  const { initialData = null, immediate = true, deps = [] } = options

  const [data, setData] = useState<T | null>(initialData as T | null)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetcher()
      setData(result)
    } catch (e) {
      const message = e instanceof Error ? e.message : '获取数据失败'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [fetcher])

  const reset = useCallback(() => {
    setData(initialData as T | null)
    setLoading(false)
    setError(null)
  }, [initialData])

  useEffect(() => {
    if (immediate) {
      refetch()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading, error, refetch, reset }
}

export default useAsyncData
