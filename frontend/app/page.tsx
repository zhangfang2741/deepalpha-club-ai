'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { TrendingUp, BarChart3, LineChart, CircleDollarSign, Activity, PieChart, Menu, X } from 'lucide-react'
import LoginRegisterForm from '@/components/auth/LoginRegisterForm'
import { useAuthStore } from '@/lib/store/auth'

const NAV_ITEMS = ['ETF 资金流', '功能介绍', '关于我们'] as const

export default function LandingPage() {
  const router = useRouter()
  const { isAuthenticated, hydrated, hydrate } = useAuthStore()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    hydrate()
  }, [hydrate])

  useEffect(() => {
    if (hydrated && isAuthenticated) {
      router.replace('/dashboard')
    }
  }, [hydrated, isAuthenticated, router])

  return (
    <div className="min-h-screen bg-[#f0f4ff] text-slate-900 flex flex-col overflow-hidden">
      {/* 顶部导航 */}
      <nav className="border-b border-blue-700 bg-blue-600 px-6 sm:px-8 flex-shrink-0">
        <div className="h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-white text-blue-600 rounded-lg flex items-center justify-center shadow-sm">
              <TrendingUp className="w-5 h-5" />
            </div>
            <span className="font-bold text-white text-xl tracking-tight">DeepAlpha</span>
          </div>

          {/* 桌面端导航 */}
          <div className="hidden sm:flex items-center gap-6 text-sm text-blue-100">
            {NAV_ITEMS.map((item) => (
              <span key={item} className="hover:text-white cursor-default transition-colors">{item}</span>
            ))}
          </div>

          {/* 移动端汉堡按钮 */}
          <button
            className="sm:hidden text-white p-1 rounded-md hover:bg-blue-700/50 transition-colors"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="菜单"
          >
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* 移动端下拉菜单 */}
        {menuOpen && (
          <div className="sm:hidden border-t border-blue-700/60 py-2 flex flex-col">
            {NAV_ITEMS.map((item) => (
              <span
                key={item}
                className="px-2 py-2.5 text-sm text-blue-100 hover:text-white hover:bg-blue-700/40 rounded-md cursor-default transition-colors"
                onClick={() => setMenuOpen(false)}
              >
                {item}
              </span>
            ))}
          </div>
        )}
      </nav>

      {/* 主体 */}
      <div className="relative flex-1 flex items-center">

        {/* 背景半透明金融科技图标 */}
        <BarChart3        className="absolute top-8   left-12  w-32 h-32 text-blue-600/[0.08] rotate-[-12deg]" />
        <LineChart        className="absolute bottom-12 left-1/4 w-40 h-40 text-blue-600/[0.07] rotate-[8deg]" />
        <PieChart         className="absolute top-1/4  left-1/2 w-24 h-24 text-blue-600/[0.07] rotate-[15deg]" />
        <Activity         className="absolute bottom-8 right-16  w-36 h-36 text-blue-600/[0.08] rotate-[-6deg]" />
        <CircleDollarSign className="absolute top-12 right-1/4 w-28 h-28 text-blue-600/[0.07] rotate-[20deg]" />

        <div className="max-w-7xl mx-auto px-6 sm:px-12 py-16 flex items-center gap-16 flex-wrap lg:flex-nowrap w-full relative z-10">

          {/* 左侧文案 */}
          <div className="flex-1 min-w-72 max-w-xl">
            <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-600 text-xs font-medium px-3 py-1.5 rounded-full mb-8 border border-blue-100">
              <Activity className="w-3 h-3" />
              AI 驱动的投资分析平台
            </div>

            <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-5 tracking-tight text-slate-900">
              智能分析<br />
              <span className="text-blue-600">ETF 资金流向</span><br />
              把握市场先机
            </h1>

            <p className="text-base text-slate-500 leading-relaxed max-w-md">
              AI Agent 实时解读市场动态，量化分析恐慌贪婪指数，助你在波动中做出更明智的投资决策。
            </p>

            <div className="flex gap-10 mt-10">
              {[
                { value: '实时', desc: 'ETF 资金流监控' },
                { value: 'AI',   desc: '智能对话分析' },
                { value: '量化', desc: '投资评分系统' },
              ].map(({ value, desc }) => (
                <div key={desc} className="flex flex-col gap-0.5">
                  <span className="text-2xl font-bold text-slate-900">{value}</span>
                  <span className="text-xs text-slate-500">{desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧表单 */}
          <div className="w-full max-w-sm flex-shrink-0 lg:ml-auto">
            <LoginRegisterForm />
          </div>
        </div>
      </div>

      {/* 底部版权 */}
      <footer className="border-t border-blue-100 py-4 px-8 flex items-center justify-between text-xs text-slate-400">
        <span>© 2025 DeepAlpha. All rights reserved.</span>
        <span className="hidden sm:block">AI 驱动的投资决策平台</span>
      </footer>
    </div>
  )
}
