'use client'

import { useState, useEffect } from 'react'
import { Search, ExternalLink, Building2, Loader2, X, FileText, Info, Star } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import {
  fetchCompanyFilings,
  fetchFilingDocuments,
  type CompanyFilingsResponse,
  type FilingRecord,
  type FilingDocument,
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

const CATEGORY_LABELS: Record<string, string> = {
  financials: '财报',
  material_events: '重大事件',
  insider: '内部人交易',
  ownership: '大股东与机构持仓',
  proxy: '股东会与代理',
  registration: '注册与发行',
  other: '其他',
}

function FilingRow({ f, onOpen }: { f: FilingRecord; onOpen: (f: FilingRecord) => void }) {
  const color = CATEGORY_COLORS[f.category] ?? CATEGORY_COLORS.other
  return (
    <button
      onClick={() => onOpen(f)}
      className="w-full text-left flex items-start gap-4 py-3 px-4 hover:bg-gray-50 rounded-lg transition-colors border-b border-gray-50 last:border-0"
    >
      {/* form 徽章 + 中文名 */}
      <div className="flex-shrink-0 mt-0.5 flex flex-col items-center gap-1 min-w-[72px]">
        <span className={`px-2.5 py-1 rounded-md text-xs font-bold border ${color} w-full text-center`}>
          {f.form}
        </span>
        {f.form_name && <span className="text-[11px] text-gray-500 leading-tight text-center">{f.form_name}</span>}
      </div>

      <div className="flex-1 min-w-0">
        {f.items.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 mb-1">
            {f.items.map((it) => (
              <span
                key={it.code}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-800 text-xs border border-amber-100"
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

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>
            提交日 <span className="font-medium text-gray-700 tabular-nums">{f.filing_date || '—'}</span>
          </span>
          <span>
            报告期 <span className="font-medium text-gray-700 tabular-nums">{f.report_date || '—'}</span>
          </span>
          <span className="font-mono text-gray-400">{f.accession_number}</span>
        </div>
      </div>

      <span className="flex-shrink-0 mt-0.5 p-1.5 text-gray-300">
        <Info className="w-4 h-4" />
      </span>
    </button>
  )
}

function DocumentList({ cik, accession }: { cik: string; accession: string }) {
  const [docs, setDocs] = useState<FilingDocument[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(false)
    fetchFilingDocuments(cik, accession)
      .then((res) => {
        if (alive) setDocs(res.documents)
      })
      .catch(() => {
        if (alive) setError(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [cik, accession])

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 py-3">
        <Loader2 className="w-4 h-4 animate-spin" /> 正在读取文件清单…
      </div>
    )
  }
  if (error || !docs || docs.length === 0) {
    return <div className="text-sm text-gray-400 py-2">未能读取文件清单，可用下方按钮打开 SEC 目录。</div>
  }

  return (
    <div>
      <div className="text-xs text-gray-400 mb-2">文件清单（★ 为业绩新闻稿/重点材料）</div>
      <div className="space-y-1.5">
        {docs.map((d) => (
          <a
            key={d.filename}
            href={d.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border transition-colors ${
              d.highlight
                ? 'bg-amber-50 border-amber-200 hover:border-amber-300'
                : 'bg-white border-gray-100 hover:border-blue-200'
            }`}
          >
            {d.highlight ? (
              <Star className="w-4 h-4 text-amber-500 flex-shrink-0 fill-amber-400" />
            ) : (
              <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <div className={`text-sm ${d.highlight ? 'text-amber-900 font-medium' : 'text-gray-700'}`}>
                {d.label || d.type || d.filename}
              </div>
              {d.type && <div className="text-[11px] text-gray-400 font-mono">{d.type}</div>}
            </div>
            <ExternalLink className="w-3.5 h-3.5 text-gray-300 flex-shrink-0" />
          </a>
        ))}
      </div>
    </div>
  )
}

function DetailModal({
  f,
  company,
  cik,
  onClose,
}: {
  f: FilingRecord
  company: string
  cik: string
  onClose: () => void
}) {
  const color = CATEGORY_COLORS[f.category] ?? CATEGORY_COLORS.other
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-start justify-between p-5 border-b border-gray-100">
          <div className="flex items-start gap-3">
            <span className={`px-3 py-1.5 rounded-lg text-sm font-bold border ${color}`}>{f.form}</span>
            <div>
              <div className="text-lg font-bold text-gray-900">{f.form_name || f.form}</div>
              <div className="text-xs text-gray-400 mt-0.5">
                {company} · {CATEGORY_LABELS[f.category] ?? '其他'}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* 表格解释 */}
          {f.form_desc && (
            <div className="flex gap-2.5 p-3.5 rounded-xl bg-blue-50 border border-blue-100">
              <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-blue-900 leading-relaxed">{f.form_desc}</p>
            </div>
          )}

          {/* 关键信息 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">提交日</div>
              <div className="text-sm font-semibold text-gray-800 tabular-nums">{f.filing_date || '—'}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">报告期</div>
              <div className="text-sm font-semibold text-gray-800 tabular-nums">{f.report_date || '—'}</div>
            </div>
            <div className="col-span-2">
              <div className="text-xs text-gray-400 mb-1">Accession Number</div>
              <div className="text-sm font-mono text-gray-700">{f.accession_number}</div>
            </div>
            {f.primary_doc_description && (
              <div className="col-span-2">
                <div className="text-xs text-gray-400 mb-1">主文档</div>
                <div className="text-sm text-gray-700">{f.primary_doc_description}</div>
              </div>
            )}
          </div>

          {/* 8-K item 明细 */}
          {f.items.length > 0 && (
            <div>
              <div className="text-xs text-gray-400 mb-2">披露事项（8-K Items）</div>
              <div className="space-y-1.5">
                {f.items.map((it) => (
                  <div key={it.code} className="flex items-center gap-2 text-sm">
                    <span className="font-mono font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded text-xs">
                      {it.code}
                    </span>
                    <span className="text-gray-700">{it.label || '（未知事项）'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 文件清单（懒加载） */}
          <DocumentList cik={cik} accession={f.accession_number} />

          {/* SEC 目录入口 */}
          {f.index_url && (
            <a
              href={f.index_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              在 SEC EDGAR 打开完整目录
            </a>
          )}

          <p className="text-xs text-gray-400 border-t border-gray-100 pt-3">
            正文抓取与中文翻译将在后续版本提供，当前可点击文件查看 SEC 原文。财报电话会议逐字记录（Q&A）SEC 不收录，需付费源。
          </p>
        </div>
      </div>
    </div>
  )
}

export default function SecFilingsPage() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState<CompanyFilingsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeCat, setActiveCat] = useState<string>('all')
  const [selected, setSelected] = useState<FilingRecord | null>(null)

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

  const visibleFilings: FilingRecord[] =
    data == null
      ? []
      : activeCat === 'all'
        ? data.categories.flatMap((c) => c.filings)
        : (data.categories.find((c) => c.key === activeCat)?.filings ?? [])

  const sortedVisible =
    activeCat === 'all'
      ? [...visibleFilings].sort((a, b) => (a.filing_date < b.filing_date ? 1 : -1))
      : visibleFilings

  return (
    <DashboardShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Building2 className="w-6 h-6 text-blue-600" />
            SEC 文件浏览
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            输入股票代码或 CIK，查看该公司在 SEC EDGAR 提交的全部文件，按类型自动分类。数据来源：SEC EDGAR 官方接口。
          </p>
        </div>

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
                  <div className="text-2xl font-bold text-blue-600 tabular-nums">{data.total.toLocaleString()}</div>
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
                全部 <span className="opacity-70 tabular-nums">{data.total}</span>
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
                  {c.label} <span className="opacity-70 tabular-nums">{c.count}</span>
                </button>
              ))}
            </div>

            {/* filing 列表 */}
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
              {sortedVisible.length === 0 ? (
                <div className="py-12 text-center text-gray-400 text-sm">该分类下暂无文件</div>
              ) : (
                <div className="p-2 max-h-[calc(100vh-360px)] overflow-y-auto">
                  {sortedVisible.map((f, i) => (
                    <FilingRow key={`${f.accession_number}-${i}`} f={f} onOpen={setSelected} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {selected && (
        <DetailModal
          f={selected}
          company={data?.company.name ?? ''}
          cik={data?.company.cik ?? ''}
          onClose={() => setSelected(null)}
        />
      )}
    </DashboardShell>
  )
}
