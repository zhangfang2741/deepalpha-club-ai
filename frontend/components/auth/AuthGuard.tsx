'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'

interface AuthGuardProps {
  children: React.ReactNode
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter()
  const { isAuthenticated, hydrated, hydrate } = useAuthStore()

  // 挂载时从 localStorage 恢复登录状态
  useEffect(() => {
    hydrate()
  }, [hydrate])

  // hydrate 完成后，若未登录则跳转落地页
  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      router.replace('/')
    }
  }, [hydrated, isAuthenticated, router])

  // hydrate 执行中：显示加载占位（避免未登录内容闪烁）
  if (!hydrated) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
      </div>
    )
  }

  // hydrate 完成但未登录：显示空内容（useEffect 正在执行跳转）
  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}
