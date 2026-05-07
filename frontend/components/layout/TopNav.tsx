'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'

const NAV_ITEMS = [
  { href: '/dashboard', label: '仪表盘' },
  { href: '/fear-greed', label: '恐慌指数' },
  { href: '/etf', label: 'ETF 资金流' },
  { href: '/chat', label: 'AI 对话' },
  { href: '/settings', label: '设置' },
] as const

export default function TopNav() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, clearAuth } = useAuthStore()

  const handleLogout = () => {
    clearAuth()
    router.push('/')
  }

  const displayName = user?.username ?? user?.email ?? '账户'

  return (
    <nav className="h-14 border-b border-gray-200 bg-white px-6 flex items-center gap-6 flex-shrink-0">
      <Link
        href="/dashboard"
        className="font-bold text-gray-900 text-base flex-shrink-0 hover:text-gray-700 transition-colors"
      >
        DeepAlpha
      </Link>

      <div className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              {item.label}
            </Link>
          )
        })}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-sm text-gray-500">{displayName}</span>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-md hover:bg-gray-50 transition-colors"
        >
          退出
        </button>
      </div>
    </nav>
  )
}
