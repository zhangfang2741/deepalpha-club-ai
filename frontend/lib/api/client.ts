// frontend/lib/api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

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
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
