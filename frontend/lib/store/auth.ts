// frontend/lib/store/auth.ts
import { create } from 'zustand'
import type { AuthUser } from '@/lib/api/auth'

interface AuthState {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  hydrated: boolean  // hydrate() 是否已执行，用于防止 AuthGuard 在检查完成前跳转

  setAuth: (token: string, user: AuthUser | null) => void
  clearAuth: () => void
  hydrate: () => void  // 从 localStorage 恢复状态（客户端调用）
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  hydrated: false,

  setAuth: (token, user) => {
    localStorage.setItem('access_token', token)
    set({ token, user, isAuthenticated: true })
  },

  clearAuth: () => {
    localStorage.removeItem('access_token')
    set({ token: null, user: null, isAuthenticated: false })
  },

  hydrate: () => {
    const token = localStorage.getItem('access_token')
    if (token) {
      set({ token, isAuthenticated: true, hydrated: true })
    } else {
      set({ token: null, user: null, isAuthenticated: false, hydrated: true })
    }
  },
}))
