import LoginRegisterForm from '@/components/auth/LoginRegisterForm'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* 顶部导航（未登录态，无页面链接） */}
      <nav className="h-14 border-b border-gray-200 bg-white/80 backdrop-blur-sm px-6 flex items-center justify-between">
        <span className="font-bold text-gray-900 text-base">DeepAlpha</span>
        <div className="flex items-center gap-5 text-sm text-gray-500">
          <span>ETF 资金流</span>
          <span>功能介绍</span>
        </div>
      </nav>

      {/* Hero + 表单 */}
      <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 flex items-center gap-16 flex-wrap">
        {/* 左侧：Hero 文案 */}
        <div className="flex-1 min-w-72 max-w-xl">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-600 text-xs font-medium px-3 py-1 rounded-full mb-6 border border-blue-100">
            AI 驱动的投资分析
          </div>
          <h1 className="text-4xl font-bold text-gray-900 leading-tight mb-4">
            AI 驱动的<br />投资决策平台
          </h1>
          <p className="text-lg text-gray-500 leading-relaxed mb-8">
            智能分析 ETF 资金流向，AI Agent 实时解读市场动态，助你把握投资机会。
          </p>
          <div className="flex gap-3 flex-wrap">
            <span className="px-5 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium cursor-default">
              免费开始
            </span>
            <span className="px-5 py-2.5 border border-gray-200 text-gray-700 rounded-lg text-sm font-medium cursor-default">
              了解更多
            </span>
          </div>
        </div>

        {/* 右侧：登录/注册表单 */}
        <div className="flex-shrink-0">
          <LoginRegisterForm />
        </div>
      </div>
    </div>
  )
}
