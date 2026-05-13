'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { TrendingUp, BarChart3, LineChart, CircleDollarSign, Activity, PieChart } from 'lucide-react'
import LoginRegisterForm from '@/components/auth/LoginRegisterForm'
import { useAuthStore } from '@/lib/store/auth'

export default function LandingPage() {
  const router = useRouter()
  const { isAuthenticated, hydrated, hydrate } = useAuthStore()

  useEffect(() => {
    hydrate()
  }, [hydrate])

  useEffect(() => {
    if (hydrated && isAuthenticated) {
      router.replace('/dashboard')
    }
  }, [hydrated, isAuthenticated, router])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col overflow-hidden">
      {/* 顶部导航 */}
      <nav className="h-16 border-b border-blue-700 bg-blue-600 px-8 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-white text-blue-600 rounded-lg flex items-center justify-center shadow-sm">
            <TrendingUp className="w-5 h-5" />
          </div>
          <span className="font-bold text-white text-xl tracking-tight">DeepAlpha</span>
        </div>
        <div className="hidden sm:flex items-center gap-6 text-sm text-blue-100">
          <span className="hover:text-white cursor-default transition-colors">ETF 资金流</span>
          <span className="hover:text-white cursor-default transition-colors">功能介绍</span>
          <span className="hover:text-white cursor-default transition-colors">关于我们</span>
        </div>
      </nav>

      {/* 主体 */}
      <div className="relative flex-1 flex items-center">

        {/* 背景半透明金融科技图标 */}
        <BarChart3  className="absolute top-8   left-12  w-32 h-32 text-blue-400/10 rotate-[-12deg]" />
        <LineChart  className="absolute bottom-12 left-1/4 w-40 h-40 text-indigo-400/10 rotate-[8deg]" />
        <PieChart   className="absolute top-1/4  left-1/2 w-24 h-24 text-blue-300/10 rotate-[15deg]" />
        <Activity   className="absolute bottom-8 right-16  w-36 h-36 text-cyan-400/10 rotate-[-6deg]" />
        <CircleDollarSign className="absolute top-12 right-1/4 w-28 h-28 text-blue-400/10 rotate-[20deg]" />

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
                  <span className="text-xs text-slate-400">{desc}</span>
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
      <footer className="border-t border-slate-100 py-4 px-8 flex items-center justify-between text-xs text-slate-400 bg-white/60">
        <span>© 2025 DeepAlpha. All rights reserved.</span>
        <span className="hidden sm:block">AI 驱动的投资决策平台</span>
      </footer>
    </div>
  )
}
