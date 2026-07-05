'use client'

import { useState } from 'react'
import { Search, ExternalLink, Building2, Loader2 } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import {
  fetchCompanyFilings,
  type CompanyFilingsResponse,
  type FilingRecord,
} from '@/lib/api/sec_filings'

// 分类 key -> 徽章配色（保持与蓝色主题协调）
const CATEGORY_COLORS: Record<string, string> = {
  financials: 'bg-blue-100 text-blue-700 border-blue-200',
  material_events: 'bg-amber-100 text-amber-700 border-amber-200',
  insider: 'bg-purple-100 text-purple-700 border-purple-200',
  ownership: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  proxy: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  registration: 'bg-rose-100 text-rose-700 border-rose-200',
  other: 'bg-gray-100 text-gray-600 border-gray-200',
}

function FilingRow({ f }: { f: FilingRecord }) {
  const color = CATEGORY_COLORS[f.category] ?? CATEGORY_COLORS.other
  const link = f.index_url || f.doc_url
  return (
    <div className="flex items-start gap-4 py-3 px-4 hover:bg-gray-50 rounded-lg transition-colors border-b border-gray-50 last:border-0">
      {/* form 徽章 */}
      <span
        className={`flex-shrink-0 mt-0.5 px-2.5 py-1 rounded-md text-xs font-bold border ${color} min-w-[64px] text-center`}
      >
        {f.form}
      </span>

      <div className="flex-1 min-w-0">
        {/* 8-K item 明细 或 文档描述 */}
        {f.items.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 mb-1">
            {f.items.map((it) => (
              <span
                key={it.code}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-800 text-xs border border-amber-100"
                title={`Item ${it.code}`}
              >
                <span className="font-mono font-semibold">{it.code}</span>
                {it.label && <span>{it.label}</span>}
              </span>
            ))}
          </div>
        ) : (
          f.primary_doc_description && (
            <div className="text-sm text-gray-700 mb-1 truncate" title={f.primary_doc_description}>
              {f.primary_doc_description}
            </div>
          )
        )}

        {/* 双日期 */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>
            提交日 <span className="font-medium text-gray-700">{f.filing_date || '—'}</span>
          </span>
          <span>
            报告期 <span className="font-medium text-gray-700">{f.report_date || '—'}</span>
          </span>
          <span className="font-mono text-gray-400">{f.accession_number}</span>
        </div>
      </div>

      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-shrink-0 mt-0.5 p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
          title="在 SEC EDGAR 打开"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      )}
    </div>
  )
}

export default function SecFilingsPage() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState<CompanyFilingsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeCat, setActiveCat] = useState<string>('all')

  const load = async (q: string) => {
    const trimmed = q.trim()
    if (!trimmed) return
    setLoading(true)
    setError('')
    try {
      const res = await fetchCompanyFilings(trimmed)
      setData(res)
      setActiveCat('all')
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      setError(status === 404 ? `未找到「${trimmed}」对应的公司，请确认股票代码或 CIK` : '数据加载失败，请稍后重试')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    load(query)
  }

  // 当前展示的 filing 列表
  const visibleFilings: FilingRecord[] =
    data == null
      ? []
      : activeCat === 'all'
        ? data.categories.flatMap((c) => c.filings)
        : (data.categories.find((c) => c.key === activeCat)?.filings ?? [])

  // "全部" 视图按提交日倒序合并
  const sortedVisible =
    activeCat === 'all'
      ? [...visibleFilings].sort((a, b) => (a.filing_date < b.filing_date ? 1 : -1))
      : visibleFilings

  return (
    <DashboardShell>
      <div className="space-y-6">
        {/* 标题 */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Building2 className="w-6 h-6 text-blue-600" />
            SEC 文件浏览
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            输入股票代码或 CIK，查看该公司在 SEC EDGAR 提交的全部文件，按类型自动分类。数据来源：SEC EDGAR 官方接口。
          </p>
        </div>

        {/* 搜索框 */}
        <form onSubmit={handleSubmit} className="flex gap-2 max-w-md">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase())}
              placeholder="股票代码或 CIK，如 AAPL / 320193"
              className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-gray-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 outline-none text-sm transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            查询
          </button>
        </form>

        {error && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-100 text-red-700 text-sm">{error}</div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center py-20 text-gray-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            正在从 SEC 拉取全部文件…
          </div>
        )}

        {data && (
          <>
            {/* 公司信息头 */}
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                  <div className="text-lg font-bold text-gray-900">{data.company.name || '未知公司'}</div>
                  <div className="flex flex-wrap items-center gap-2 mt-1.5 text-sm text-gray-500">
                    {data.company.tickers.map((t) => (
                      <span key={t} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-semibold text-xs">
                        {t}
                      </span>
                    ))}
                    <span className="text-gray-400">CIK {data.company.cik}</span>
                    {data.company.exchanges.length > 0 && (
                      <span className="text-gray-400">· {data.company.exchanges.join(', ')}</span>
                    )}
                  </div>
                  {data.company.sic_description && (
                    <div className="text-xs text-gray-400 mt-1">{data.company.sic_description}</div>
                  )}
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-blue-600">{data.total.toLocaleString()}</div>
                  <div className="text-xs text-gray-400">份文件</div>
                </div>
              </div>
            </div>

            {/* 分类筛选 chips */}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setActiveCat('all')}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-all ${
                  activeCat === 'all'
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300'
                }`}
              >
                全部 <span className="opacity-70">{data.total}</span>
              </button>
              {data.categories.map((c) => (
                <button
                  key={c.key}
                  onClick={() => setActiveCat(c.key)}
                  disabled={c.count === 0}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                    activeCat === c.key
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300'
                  }`}
                >
                  {c.label} <span className="opacity-70">{c.count}</span>
                </button>
              ))}
            </div>

            {/* filing 列表 */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm divide-y divide-gray-50">
              {sortedVisible.length === 0 ? (
                <div className="py-12 text-center text-gray-400 text-sm">该分类下暂无文件</div>
              ) : (
                <div className="p-2 max-h-[calc(100vh-360px)] overflow-y-auto">
                  {sortedVisible.map((f, i) => (
                    <FilingRow key={`${f.accession_number}-${i}`} f={f} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </DashboardShell>
  )
}
