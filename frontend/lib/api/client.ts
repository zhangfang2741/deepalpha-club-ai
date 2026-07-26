// frontend/lib/api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios'

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// 请求拦截器：自动带上 Authorization: Bearer token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

// 响应拦截器：401 清除 token 并跳转落地页
// 注意：不能在此导入 store（循环依赖），直接操作 localStorage
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // 如果是登录或注册接口报错 401，不要自动跳转，让页面处理逻辑
      const isAuthRequest = error.config?.url?.includes('/api/v1/auth/login') || 
                           error.config?.url?.includes('/api/v1/auth/register')

      if (!isAuthRequest && typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

/**
 * 从异常中提取给用户看的错误信息。
 *
 * 后端（FastAPI）出错时会在响应体 `detail` 里放可读的中文原因
 * （如「数据源返回错误：...」「未获取到 XXX 的K线数据」）。
 * axios 默认的 `error.message` 只会是「Request failed with status code 400」
 * 这类通用信息，会把真正的原因吞掉，因此这里优先取 `detail`。
 */
export function getApiErrorMessage(err: unknown, fallback = '请求失败，请稍后再试'): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    // FastAPI 参数校验错误时 detail 是数组，取第一条的 msg
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown }
      if (typeof first?.msg === 'string' && first.msg.trim()) return first.msg
    }
    if (err.message) return err.message
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

export default apiClient
