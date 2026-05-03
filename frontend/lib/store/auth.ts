// frontend/lib/store/auth.ts
import { create } from 'zustand'
import { login as apiLogin, logout as apiLogout, getMe, User } from '@/lib/api/auth'

interface AuthState {
  user: User | null
  token: string | null
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  // 初始状态：从 localStorage 恢复 token
  user: null,
  token: typeof window !== 'undefined' ? localStorage.getItem('access_token') : null,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const { access_token } = await apiLogin(email, password)
      localStorage.setItem('access_token', access_token)
      const user = await getMe()
      set({ user, token: access_token, isLoading: false })
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '登录失败，请检查邮箱和密码'
      set({ error: message, isLoading: false })
      throw err
    }
  },

  logout: async () => {
    set({ isLoading: true })
    try {
      await apiLogout()
    } finally {
      localStorage.removeItem('access_token')
      set({ user: null, token: null, isLoading: false })
    }
  },

  fetchMe: async () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) return
    set({ isLoading: true })
    try {
      const user = await getMe()
      set({ user, isLoading: false })
    } catch {
      // token 无效或已过期，清除本地状态
      localStorage.removeItem('access_token')
      set({ user: null, token: null, isLoading: false })
    }
  },

  clearError: () => set({ error: null }),
}))
