import { AxiosError } from 'axios'

interface ApiErrorResponse {
  detail?: string | { msg: string }[]
  message?: string
}

/**
 * 从 API 错误中提取用户友好的错误信息
 */
export function getErrorMessage(error: unknown): string {
  // Axios 错误
  if (error instanceof AxiosError) {
    const data = error.response?.data as ApiErrorResponse | undefined

    // FastAPI 风格的 detail 字段
    if (data?.detail) {
      if (typeof data.detail === 'string') {
        return data.detail
      }
      // 验证错误数组
      if (Array.isArray(data.detail) && data.detail.length > 0) {
        return data.detail[0].msg
      }
    }

    // 通用 message 字段
    if (data?.message) {
      return data.message
    }

    // HTTP 状态码对应的默认消息
    const statusMessages: Record<number, string> = {
      400: '请求参数错误',
      401: '请先登录',
      403: '没有权限',
      404: '资源不存在',
      422: '数据验证失败',
      429: '请求过于频繁，请稍后再试',
      500: '服务器内部错误',
      502: '网关错误',
      503: '服务暂时不可用',
    }

    if (error.response?.status && statusMessages[error.response.status]) {
      return statusMessages[error.response.status]
    }

    // 网络错误
    if (error.code === 'ECONNABORTED') {
      return '请求超时，请检查网络连接'
    }
    if (error.code === 'ERR_NETWORK') {
      return '网络连接失败'
    }
  }

  // 普通 Error
  if (error instanceof Error) {
    return error.message
  }

  // 未知错误
  return '发生未知错误'
}

/**
 * 判断是否为认证错误（需要重新登录）
 */
export function isAuthError(error: unknown): boolean {
  if (error instanceof AxiosError) {
    return error.response?.status === 401
  }
  return false
}

/**
 * 判断是否为网络错误
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof AxiosError) {
    return error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED'
  }
  return false
}
