'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'
import {
  LogOut, User, LayoutDashboard, TrendingUp, BarChart3,
  LineChart, MessageSquare, Settings, Menu, X,
} from 'lucide-react'

const NAV_ITEMS = [
  { href: '/dashboard',  label: '仪表盘',   icon: LayoutDashboard },
  { href: '/fear-greed', label: '恐慌指数', icon: TrendingUp },
  { href: '/etf',        label: 'ETF 资金流', icon: BarChart3 },
  { href: '/analysis',   label: '投资评分', icon: LineChart },
  { href: '/chat',       label: 'AI 对话',  icon: MessageSquare },
  { href: '/settings',   label: '设置',     icon: Settings },
] as const

export default function TopNav() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, clearAuth } = useAuthStore()
  const [menuOpen, setMenuOpen] = useState(false)

  const handleLogout = () => {
    clearAuth()
    router.push('/')
  }

  const displayName = user?.username ?? user?.email ?? '账户'

  return (
    <nav className="border-b border-blue-700 bg-blue-600 flex-shrink-0 shadow-sm">
      <div className="h-16 px-4 sm:px-8 flex items-center gap-4 sm:gap-8">

        {/* 移动端汉堡按钮 */}
        <button
          className="sm:hidden p-1.5 text-white hover:bg-blue-700/50 rounded-lg transition-colors flex-shrink-0"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="菜单"
        >
          {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        {/* Logo */}
        <Link
          href="/dashboard"
          className="font-bold text-white text-xl flex items-center gap-2 flex-shrink-0 hover:opacity-90 transition-opacity"
        >
          <div className="w-8 h-8 bg-white text-blue-600 rounded-lg flex items-center justify-center shadow-sm">
            <TrendingUp className="w-5 h-5" />
          </div>
          <span className="tracking-tight">DeepAlpha</span>
        </Link>

        {/* 桌面端导航 */}
        <div className="hidden sm:flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-all ${
                  isActive
                    ? 'bg-blue-700 text-white shadow-inner'
                    : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-blue-200'}`} />
                {item.label}
              </Link>
            )
          })}
        </div>

        {/* 用户信息 + 退出 */}
        <div className="ml-auto flex items-center gap-3 sm:gap-6">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-500/50 flex items-center justify-center border border-blue-400/30">
              <User className="w-4 h-4 text-blue-100" />
            </div>
            <div className="hidden sm:flex flex-col">
              <span className="text-sm font-medium text-white leading-tight">{displayName}</span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="退出登录"
            className="p-2 text-blue-100 hover:text-white hover:bg-blue-500/40 rounded-lg transition-all"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* 移动端下拉菜单 */}
      {menuOpen && (
        <div className="sm:hidden border-t border-blue-700/60 bg-blue-600 pb-2 px-3 flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className={`flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-blue-700 text-white'
                    : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                }`}
              >
                <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-blue-200'}`} />
                {item.label}
              </Link>
            )
          })}
        </div>
      )}
    </nav>
  )
}
