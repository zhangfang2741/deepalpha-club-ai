'use client'

import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'
import {
  LogOut, User, LayoutDashboard, TrendingUp, BarChart3,
  LineChart, MessageSquare, Settings, Menu, X, FlaskConical, Network,
  ArrowUpRight, Activity, Search, CandlestickChart, Waves, Cloud, Radar,
  FileText, ChevronDown, Gauge, Landmark, BookOpen, Sparkles,
  type LucideIcon,
} from 'lucide-react'

type NavLeaf = { href: string; label: string; icon: LucideIcon }
type NavGroup = { label: string; icon: LucideIcon; items: NavLeaf[] }
type NavEntry = NavLeaf | NavGroup

const isGroup = (entry: NavEntry): entry is NavGroup => 'items' in entry

// 导航结构:独立项 + 二级菜单分组
const NAV_ENTRIES: NavEntry[] = [
  { href: '/dashboard', label: '仪表盘', icon: LayoutDashboard },
  {
    label: '市场情绪',
    icon: Gauge,
    items: [
      { href: '/fear-greed',     label: '恐慌指数',   icon: TrendingUp },
      { href: '/industry-panic', label: '行业恐慌',   icon: Activity },
      { href: '/etf',            label: 'ETF 资金流', icon: BarChart3 },
    ],
  },
  {
    label: '技术分析',
    icon: LineChart,
    items: [
      { href: '/chan',     label: '缠论分析',   icon: CandlestickChart },
      { href: '/wyckoff',  label: '威科夫',     icon: Waves },
      { href: '/ichimoku', label: '一目均衡表', icon: Cloud },
    ],
  },
  {
    label: '机构动向',
    icon: Landmark,
    items: [
      { href: '/analyst-upgrades',      label: '分析师上调', icon: ArrowUpRight },
      { href: '/institutional-signals', label: '机构信号',   icon: Radar },
    ],
  },
  {
    label: '深度研究',
    icon: BookOpen,
    items: [
      { href: '/industry-research', label: '行业研究',   icon: Search },
      { href: '/company-research',  label: '企业研究',   icon: FileText },
      { href: '/supply-chain',      label: '产业图谱',   icon: Network },
      { href: '/supply-graph',      label: '供应链图谱', icon: Network },
    ],
  },
  {
    label: 'AI 工具',
    icon: Sparkles,
    items: [
      { href: '/chat',            label: 'AI 对话', icon: MessageSquare },
      { href: '/skill-generator', label: '因子探索', icon: FlaskConical },
    ],
  },
  { href: '/settings', label: '设置', icon: Settings },
]

export default function TopNav() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, clearAuth } = useAuthStore()
  const [menuOpen, setMenuOpen] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const [openMobileGroup, setOpenMobileGroup] = useState<string | null>(null)
  const navRef = useRef<HTMLDivElement>(null)

  // 点击导航区域外部时关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenGroup(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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
        <div ref={navRef} className="hidden sm:flex items-center gap-1">
          {NAV_ENTRIES.map((entry) => {
            if (!isGroup(entry)) {
              const isActive = pathname === entry.href
              const Icon = entry.icon
              return (
                <Link
                  key={entry.href}
                  href={entry.href}
                  className={`px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-all ${
                    isActive
                      ? 'bg-blue-700 text-white shadow-inner'
                      : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-blue-200'}`} />
                  {entry.label}
                </Link>
              )
            }

            const Icon = entry.icon
            const isOpen = openGroup === entry.label
            const hasActiveChild = entry.items.some((i) => i.href === pathname)
            return (
              <div
                key={entry.label}
                className="relative"
                onMouseEnter={() => setOpenGroup(entry.label)}
                onMouseLeave={() => setOpenGroup(null)}
              >
                <button
                  onClick={() => setOpenGroup((v) => (v === entry.label ? null : entry.label))}
                  className={`px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-all ${
                    hasActiveChild
                      ? 'bg-blue-700 text-white shadow-inner'
                      : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${hasActiveChild ? 'text-white' : 'text-blue-200'}`} />
                  {entry.label}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>

                {isOpen && (
                  <div className="absolute left-0 top-full pt-1 z-50 min-w-[200px]">
                    <div className="bg-white rounded-xl shadow-lg border border-gray-100 py-1.5 flex flex-col">
                      {entry.items.map((item) => {
                        const isActive = pathname === item.href
                        const ItemIcon = item.icon
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            onClick={() => setOpenGroup(null)}
                            className={`mx-1.5 px-3 py-2 rounded-lg text-sm font-medium flex items-center gap-2.5 transition-colors ${
                              isActive
                                ? 'bg-blue-50 text-blue-700'
                                : 'text-gray-700 hover:bg-gray-50 hover:text-blue-600'
                            }`}
                          >
                            <ItemIcon className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                            {item.label}
                          </Link>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
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
          {NAV_ENTRIES.map((entry) => {
            if (!isGroup(entry)) {
              const isActive = pathname === entry.href
              const Icon = entry.icon
              return (
                <Link
                  key={entry.href}
                  href={entry.href}
                  onClick={() => setMenuOpen(false)}
                  className={`flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-blue-700 text-white'
                      : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                  }`}
                >
                  <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-blue-200'}`} />
                  {entry.label}
                </Link>
              )
            }

            const Icon = entry.icon
            const isOpen = openMobileGroup === entry.label
            const hasActiveChild = entry.items.some((i) => i.href === pathname)
            return (
              <div key={entry.label} className="flex flex-col">
                <button
                  onClick={() => setOpenMobileGroup((v) => (v === entry.label ? null : entry.label))}
                  className={`flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-all ${
                    hasActiveChild
                      ? 'bg-blue-700/60 text-white'
                      : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0 text-blue-200" />
                  {entry.label}
                  <ChevronDown className={`w-4 h-4 ml-auto transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>

                {isOpen && (
                  <div className="flex flex-col gap-0.5 pl-4 mt-0.5 mb-1 border-l border-blue-500/40 ml-4">
                    {entry.items.map((item) => {
                      const isActive = pathname === item.href
                      const ItemIcon = item.icon
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          onClick={() => {
                            setMenuOpen(false)
                            setOpenMobileGroup(null)
                          }}
                          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                            isActive
                              ? 'bg-blue-700 text-white'
                              : 'text-blue-100 hover:text-white hover:bg-blue-500/40'
                          }`}
                        >
                          <ItemIcon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-white' : 'text-blue-200'}`} />
                          {item.label}
                        </Link>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </nav>
  )
}
