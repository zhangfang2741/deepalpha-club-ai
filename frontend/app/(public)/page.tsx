'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { TrendingUp, BarChart3, MessageSquare, Shield, Zap, LineChart } from 'lucide-react'
import LoginRegisterForm from '@/components/auth/LoginRegisterForm'
import { useAuthStore } from '@/lib/store/auth'

const FEATURE_CHIPS = [
  { icon: BarChart3, label: 'ETF 资金流' },
  { icon: TrendingUp, label: '恐慌贪婪指数' },
  { icon: LineChart, label: '投资评分' },
  { icon: MessageSquare, label: 'AI 对话' },
  { icon: Shield, label: '安全可靠' },
] as const

const STATS = [
  { value: '实时', desc: 'ETF 资金流监控' },
  { value: 'AI', desc: '智能对话分析' },
  { value: '量化', desc: '投资评分系统' },
] as const

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
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* 顶部导航 — 与 dashboard TopNav 保持一致品牌色 */}
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

      {/* Hero + 表单区域 */}
      <div className="relative flex-1 overflow-hidden">
        {/* 背景光晕装饰 */}
        <div className="absolute top-0 left-1/4 w-[700px] h-[700px] bg-blue-600/10 rounded-full blur-3xl -translate-y-1/2 pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-blue-500/8 rounded-full blur-3xl translate-x-1/3 translate-y-1/3 pointer-events-none" />
        <div className="absolute top-1/2 left-0 w-[300px] h-[300px] bg-indigo-600/8 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2 pointer-events-none" />

        <div className="max-w-7xl mx-auto px-6 sm:px-8 pt-16 pb-20 flex items-center gap-12 lg:gap-20 flex-wrap lg:flex-nowrap relative">
          {/* 左侧：Hero 文案 */}
          <div className="flex-1 min-w-72 max-w-2xl">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-blue-500/15 text-blue-300 text-xs font-medium px-3.5 py-1.5 rounded-full mb-8 border border-blue-500/25">
              <Zap className="w-3 h-3" />
              AI 驱动的新一代投资分析平台
            </div>

            {/* 主标题 */}
            <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-5 tracking-tight">
              智能分析<br />
              <span className="text-blue-400">ETF 资金流向</span><br />
              把握市场先机
            </h1>

            {/* 副标题 */}
            <p className="text-base sm:text-lg text-slate-400 leading-relaxed mb-10 max-w-lg">
              AI Agent 实时解读市场动态，量化分析恐慌贪婪指数，助你在波动中做出更明智的投资决策。
            </p>

            {/* 核心亮点统计 */}
            <div className="flex gap-8 mb-10">
              {STATS.map(({ value, desc }) => (
                <div key={desc} className="flex flex-col gap-0.5">
                  <span className="text-2xl font-bold text-white">{value}</span>
                  <span className="text-xs text-slate-400">{desc}</span>
                </div>
              ))}
            </div>

            {/* 功能标签 */}
            <div className="flex flex-wrap gap-2">
              {FEATURE_CHIPS.map(({ icon: Icon, label }) => (
                <div
                  key={label}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/70 border border-slate-700/60 rounded-full text-xs text-slate-300 hover:border-blue-500/40 hover:text-slate-200 transition-colors"
                >
                  <Icon className="w-3 h-3 text-blue-400 flex-shrink-0" />
                  {label}
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：登录/注册表单 */}
          <div className="w-full max-w-sm flex-shrink-0 lg:ml-auto">
            <LoginRegisterForm />
          </div>
        </div>
      </div>

      {/* 底部版权 */}
      <footer className="border-t border-slate-800/60 py-4 px-8 flex items-center justify-between text-xs text-slate-600">
        <span>© 2025 DeepAlpha. All rights reserved.</span>
        <span className="hidden sm:block">AI 驱动的投资决策平台</span>
      </footer>
    </div>
  )
}
