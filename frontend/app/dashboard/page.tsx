import DashboardShell from '@/components/layout/DashboardShell'

export default function DashboardPage() {
  return (
    <DashboardShell>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">仪表盘</h1>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {(['总资产', '今日收益', '持仓数量'] as const).map((label) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-sm text-gray-500 mb-3">{label}</p>
            <div className="h-7 bg-gray-100 rounded-md animate-pulse" />
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <p className="text-sm font-medium text-gray-700 mb-4">市场概览</p>
        <div className="h-48 bg-gray-50 rounded-lg flex items-center justify-center">
          <p className="text-sm text-gray-400">图表数据即将上线</p>
        </div>
      </div>
    </DashboardShell>
  )
}
