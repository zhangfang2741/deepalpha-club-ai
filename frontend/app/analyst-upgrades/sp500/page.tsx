'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { TrendingUp, RefreshCw, Info } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import UpgradeTable from '@/components/analyst_upgrades/UpgradeTable'
import Spinner from '@/components/ui/Spinner'
import { fetchSP500Upgrades } from '@/lib/api/analyst_upgrade'
import type { SP500UpgradesResponse } from '@/lib/api/analyst_upgrade'

export default function SP500UpgradesPage() {
  const [data, setData] = useState<SP500UpgradesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = (refresh = false) => {
    setLoading(true)
    setError('')
    fetchSP500Upgrades(refresh)
      .then(setData)
      .catch(() => setError('数据加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <DashboardShell>
      <div className="space-y-6">
        {/* 页头 */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="w-5 h-5 text-blue-600" />
              <h1 className="text-xl font-bold text-gray-900">分析师持续上调</h1>
            </div>
            <p className="text-sm text-gray-500">
              筛选月均目标价 &gt; 季均 &gt; 年均的股票，按月度环比动量排序
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50 disabled:opacity-40 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>

        {/* 指数切换标签 */}
        <div className="flex gap-1 border-b border-gray-200">
          <Link
            href="/analyst-upgrades"
            className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            纳斯达克 100
          </Link>
          <span className="px-4 py-2 text-sm font-medium text-blue-600 border-b-2 border-blue-600 -mb-px">
            标普 500
          </span>
          <Link
            href="/analyst-upgrades/custom"
            className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            自定义
          </Link>
        </div>

        {/* 元信息条 */}
        {data && !loading && (
          <div className="flex flex-wrap gap-4 text-sm text-gray-500 bg-gray-50 rounded-lg px-4 py-3">
            <span>成分股 <span className="font-semibold text-gray-700">{data.total_constituents}</span> 只</span>
            <span>满足条件 <span className="font-semibold text-blue-600">{data.upgrade_count}</span> 只</span>
            <span>数据日期 <span className="font-semibold text-gray-700">{data.as_of}</span></span>
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Info className="w-3 h-3" />
              成分股每次请求动态获取，目标价数据 6h 缓存
            </span>
          </div>
        )}

        {/* 内容区 */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-24 gap-3">
            <Spinner />
            <p className="text-sm text-gray-400">正在拉取 500 只成分股数据，首次约 75 秒…</p>
          </div>
        )}

        {!loading && error && (
          <div className="text-center py-16 text-red-500 text-sm">{error}</div>
        )}

        {!loading && !error && data && data.stocks.length === 0 && (
          <div className="text-center py-16 text-gray-400 text-sm">暂无满足条件的股票</div>
        )}

        {!loading && !error && data && data.stocks.length > 0 && (
          <UpgradeTable stocks={data.stocks} />
        )}

        {/* 方法说明 */}
        <div className="text-xs text-gray-400 bg-gray-50 rounded-lg p-4 space-y-1">
          <p><span className="font-medium text-gray-500">筛选逻辑：</span>月均目标价 &gt; 季均目标价 &gt; 年均目标价，且近月至少有 2 家机构出报告</p>
          <p><span className="font-medium text-gray-500">月环比：</span>(月均 - 季均) / 季均，衡量最近一个月分析师上调的加速程度</p>
          <p><span className="font-medium text-gray-500">数据源：</span>Financial Modeling Prep (FMP) · 标普 500 成分股每次动态拉取</p>
        </div>
      </div>
    </DashboardShell>
  )
}
