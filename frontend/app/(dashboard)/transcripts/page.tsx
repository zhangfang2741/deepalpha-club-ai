'use client'

import { useMemo, useState } from 'react'
import {
  AlertCircle,
  CalendarDays,
  ExternalLink,
  FileSearch,
  FileText,
  Languages,
  ListChecks,
  MessageSquareText,
  Search,
  Sparkles,
} from 'lucide-react'
import {
  fetchTranscriptDetail,
  fetchTranscriptList,
  fetchTranscriptSummary,
  fetchTranscriptTranslation,
  TranscriptCandidate,
  TranscriptDetailResponse,
  TranscriptSummaryResponse,
  TranscriptTranslationResponse,
} from '@/lib/api/transcripts'
import DashboardShell from '@/components/layout/DashboardShell'

type DetailTab = 'summary' | 'translation' | 'qa' | 'prepared' | 'segments'

const POPULAR_TICKERS = ['NVDA', 'AAPL', 'MSFT', 'AMZN', 'META', 'TSLA', 'GOOGL', 'AMD']

function formatDate(value: string | null | undefined) {
  if (!value) return '日期未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function normalizeTicker(value: string) {
  return value.trim().toUpperCase().replace('/', '.')
}

function getErrorMessage(error: unknown, fallback: string) {
  const apiError = error as { response?: { data?: { detail?: unknown; error?: unknown } }; message?: string }
  if (apiError.response?.data?.error === 'Rate limit exceeded') {
    return '请求太频繁，请稍等几秒后再试'
  }
  const detail = apiError.response?.data?.detail ?? apiError.response?.data?.error
  if (typeof detail === 'string') return detail
  if (error instanceof Error) return error.message
  return fallback
}

export default function TranscriptsPage() {
  const [ticker, setTicker] = useState('NVDA')
  const [searchedTicker, setSearchedTicker] = useState('')
  const [transcripts, setTranscripts] = useState<TranscriptCandidate[]>([])
  const [selectedUrl, setSelectedUrl] = useState('')
  const [detail, setDetail] = useState<TranscriptDetailResponse | null>(null)
  const [activeTab, setActiveTab] = useState<DetailTab>('summary')
  const [listLoading, setListLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')

  const [summary, setSummary] = useState<TranscriptSummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState('')

  const [translation, setTranslation] = useState<TranscriptTranslationResponse | null>(null)
  const [translationLoading, setTranslationLoading] = useState(false)
  const [translationError, setTranslationError] = useState('')

  const qaSegments = useMemo(
    () => detail?.segments.filter((segment) => segment.section === 'questions_and_answers') ?? [],
    [detail]
  )

  const preparedSegments = useMemo(
    () => detail?.segments.filter((segment) => segment.section === 'prepared_remarks') ?? [],
    [detail]
  )

  const resetAiState = () => {
    setSummary(null)
    setSummaryLoading(false)
    setSummaryError('')
    setTranslation(null)
    setTranslationLoading(false)
    setTranslationError('')
  }

  const loadTranscriptDetail = async (symbol: string, transcript: TranscriptCandidate) => {
    setSelectedUrl(transcript.url)
    setDetail(null)
    setDetailLoading(true)
    setError('')
    resetAiState()

    try {
      const result = await fetchTranscriptDetail(symbol, transcript.url)
      setDetail(result)
      setActiveTab('summary')
      loadSummary(result)
    } catch (err) {
      setError(getErrorMessage(err, '逐字稿加载失败'))
    } finally {
      setDetailLoading(false)
    }
  }

  const loadSummary = async (target: TranscriptDetailResponse) => {
    setSummaryLoading(true)
    setSummaryError('')
    try {
      const result = await fetchTranscriptSummary(target)
      setSummary(result)
    } catch (err) {
      setSummaryError(getErrorMessage(err, '总结生成失败'))
    } finally {
      setSummaryLoading(false)
    }
  }

  const loadTranslation = async (target: TranscriptDetailResponse) => {
    setTranslationLoading(true)
    setTranslationError('')
    try {
      const result = await fetchTranscriptTranslation(target)
      setTranslation(result)
    } catch (err) {
      setTranslationError(getErrorMessage(err, '翻译生成失败'))
    } finally {
      setTranslationLoading(false)
    }
  }

  const handleSelectTab = (tab: DetailTab) => {
    setActiveTab(tab)
    if (!detail) return
    if (tab === 'summary' && !summary && !summaryLoading) {
      loadSummary(detail)
    }
    if (tab === 'translation' && !translation && !translationLoading) {
      loadTranslation(detail)
    }
  }

  const handleSearch = async (overrideTicker?: string) => {
    const symbol = normalizeTicker(overrideTicker ?? ticker)
    if (!symbol) {
      setError('请输入股票代码')
      return
    }

    setTicker(symbol)
    setSearchedTicker(symbol)
    setTranscripts([])
    setSelectedUrl('')
    setDetail(null)
    setError('')
    setListLoading(true)

    try {
      const result = await fetchTranscriptList(symbol)
      setTranscripts(result.transcripts)
      if (result.transcripts.length > 0) {
        await loadTranscriptDetail(symbol, result.transcripts[0])
      }
    } catch (err) {
      setError(getErrorMessage(err, '财报电话会议列表加载失败'))
    } finally {
      setListLoading(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      handleSearch()
    }
  }

  const renderTranscriptText = (text: string) => (
    <div className="space-y-4 text-sm leading-7 text-gray-700">
      {text.split('\n\n').map((paragraph, index) => (
        <p key={`${paragraph.slice(0, 24)}-${index}`}>{paragraph}</p>
      ))}
    </div>
  )

  const renderAiLoading = (label: string) => (
    <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-3 text-sm font-medium text-gray-500">
      <span className="h-6 w-6 rounded-full border-2 border-blue-200 border-t-blue-600 animate-spin" />
      <span>{label}</span>
      <span className="text-xs text-gray-400">首次生成需调用 AI，请稍候</span>
    </div>
  )

  const renderAiError = (message: string, onRetry: () => void) => (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <div className="flex items-center gap-2 text-sm font-medium text-red-700">
        <AlertCircle className="h-4 w-4" />
        <span>{message}</span>
      </div>
      <button
        onClick={onRetry}
        className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-semibold text-gray-700 transition hover:border-blue-300 hover:text-blue-700"
      >
        重试
      </button>
    </div>
  )

  const renderBulletList = (title: string, items: string[]) => {
    if (!items || items.length === 0) return null
    return (
      <div>
        <h4 className="mb-2 text-sm font-bold text-gray-900">{title}</h4>
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li key={`${title}-${index}`} className="flex gap-2 text-sm leading-6 text-gray-700">
              <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <DashboardShell>
      <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white shadow-sm">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">财报电话会议</h1>
            <p className="text-sm text-gray-500">The Motley Fool transcripts</p>
          </div>
        </div>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
          <div className="flex-1">
            <label htmlFor="transcript-ticker" className="mb-2 block text-sm font-semibold text-gray-700">
              股票代码
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                id="transcript-ticker"
                value={ticker}
                onChange={(event) => setTicker(event.target.value.toUpperCase())}
                onKeyDown={handleKeyDown}
                className="h-11 w-full rounded-lg border border-gray-200 bg-gray-50 pl-10 pr-3 text-base font-semibold tracking-wide text-gray-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                placeholder="NVDA"
              />
            </div>
          </div>
          <button
            onClick={() => handleSearch()}
            disabled={listLoading || detailLoading}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {listLoading ? (
              <span className="h-4 w-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
            ) : (
              <FileSearch className="h-4 w-4" />
            )}
            查询会议
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {POPULAR_TICKERS.map((symbol) => (
            <button
              key={symbol}
              onClick={() => handleSearch(symbol)}
              disabled={listLoading || detailLoading}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-bold text-gray-700 transition hover:border-blue-500 hover:text-blue-700 disabled:opacity-50"
            >
              {symbol}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <div>
              <h2 className="text-sm font-bold text-gray-900">
                {searchedTicker ? `${searchedTicker} 会议` : '会议列表'}
              </h2>
              <p className="text-xs text-gray-500">{transcripts.length} 条记录</p>
            </div>
            <ListChecks className="h-4 w-4 text-blue-500" />
          </div>

          <div className="max-h-[680px] overflow-y-auto p-3">
            {listLoading && transcripts.length === 0 && (
              <div className="flex h-44 items-center justify-center text-sm text-gray-500">加载中...</div>
            )}

            {!listLoading && transcripts.length === 0 && (
              <div className="flex h-44 flex-col items-center justify-center gap-2 text-center text-sm text-gray-500">
                <FileSearch className="h-8 w-8 text-gray-300" />
                <span>暂无会议记录</span>
              </div>
            )}

            <div className="space-y-2">
              {transcripts.map((item) => {
                const active = item.url === selectedUrl
                return (
                  <button
                    key={item.url}
                    onClick={() => loadTranscriptDetail(searchedTicker || normalizeTicker(ticker), item)}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      active
                        ? 'border-blue-500 bg-blue-50 shadow-sm'
                        : 'border-gray-200 bg-white hover:border-blue-200 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${
                          active ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        <CalendarDays className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="line-clamp-2 text-sm font-bold leading-5 text-gray-900">{item.title}</p>
                        <p className="mt-1 text-xs font-medium text-gray-500">{formatDate(item.published_at)}</p>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </section>

        <section className="min-h-[520px] rounded-xl border border-gray-200 bg-white shadow-sm">
          {!detail && !detailLoading && (
            <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-3 text-center text-gray-500">
              <MessageSquareText className="h-10 w-10 text-gray-300" />
              <p className="text-sm font-medium">选择一场会议查看内容</p>
            </div>
          )}

          {detailLoading && (
            <div className="flex h-full min-h-[520px] items-center justify-center">
              <div className="flex items-center gap-3 text-sm font-medium text-gray-500">
                <span className="h-5 w-5 rounded-full border-2 border-blue-200 border-t-blue-600 animate-spin" />
                加载逐字稿...
              </div>
            </div>
          )}

          {detail && !detailLoading && (
            <div className="flex min-h-[520px] flex-col">
              <div className="border-b border-gray-100 p-5">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-bold text-gray-500">
                      <span className="rounded-md bg-gray-100 px-2 py-1">{detail.ticker}</span>
                      <span>{formatDate(detail.published_date)}</span>
                      <span>{detail.source}</span>
                    </div>
                    <h2 className="text-xl font-bold leading-tight text-gray-900">{detail.title}</h2>
                  </div>
                  <a
                    href={detail.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-9 flex-shrink-0 items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-700 transition hover:border-blue-300 hover:text-blue-700"
                  >
                    <ExternalLink className="h-4 w-4" />
                    来源
                  </a>
                </div>

                <div className="mt-5 inline-flex flex-wrap rounded-lg border border-gray-200 bg-gray-50 p-1">
                  {[
                    { id: 'summary', label: '总结', icon: Sparkles },
                    { id: 'translation', label: '中文翻译', icon: Languages },
                    { id: 'qa', label: 'Q&A', icon: MessageSquareText },
                    { id: 'prepared', label: '开场陈述/业绩说明', icon: FileText },
                    { id: 'segments', label: '发言人', icon: ListChecks },
                  ].map((tab) => {
                    const Icon = tab.icon
                    const active = activeTab === tab.id
                    return (
                      <button
                        key={tab.id}
                        onClick={() => handleSelectTab(tab.id as DetailTab)}
                        className={`inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-semibold transition ${
                          active ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {tab.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="max-h-[680px] overflow-y-auto p-5">
                {activeTab === 'summary' && (
                  <div>
                    {summaryLoading && renderAiLoading('AI 正在总结电话会议要点...')}
                    {!summaryLoading && summaryError && renderAiError(summaryError, () => loadSummary(detail))}
                    {!summaryLoading && !summaryError && summary && (
                      <div className="space-y-6">
                        {summary.summary.overview && (
                          <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
                            <h4 className="mb-2 flex items-center gap-2 text-sm font-bold text-blue-800">
                              <Sparkles className="h-4 w-4" />
                              整体概述
                            </h4>
                            <p className="text-sm leading-7 text-gray-700">{summary.summary.overview}</p>
                          </div>
                        )}
                        {renderBulletList('核心要点', summary.summary.key_points)}
                        {renderBulletList('财务亮点', summary.summary.financial_highlights)}
                        {summary.summary.guidance && (
                          <div>
                            <h4 className="mb-2 text-sm font-bold text-gray-900">业绩指引与展望</h4>
                            <p className="text-sm leading-7 text-gray-700">{summary.summary.guidance}</p>
                          </div>
                        )}
                        {renderBulletList('问答要点', summary.summary.qa_highlights)}
                        {renderBulletList('风险与挑战', summary.summary.risks)}
                        <p className="border-t border-gray-100 pt-3 text-xs text-gray-400">
                          摘要由 AI 生成，仅供参考，请以原始逐字稿为准。
                        </p>
                      </div>
                    )}
                  </div>
                )}
                {activeTab === 'translation' && (
                  <div>
                    {translationLoading && renderAiLoading('AI 正在翻译逐字稿...')}
                    {!translationLoading &&
                      translationError &&
                      renderAiError(translationError, () => loadTranslation(detail))}
                    {!translationLoading && !translationError && translation && (
                      <div className="space-y-6">
                        {translation.prepared_remarks_zh && (
                          <div>
                            <h4 className="mb-3 text-sm font-bold text-blue-700">管理层发言</h4>
                            {renderTranscriptText(translation.prepared_remarks_zh)}
                          </div>
                        )}
                        {translation.questions_and_answers_zh && (
                          <div>
                            <h4 className="mb-3 text-sm font-bold text-emerald-700">问答环节 Q&amp;A</h4>
                            {renderTranscriptText(translation.questions_and_answers_zh)}
                          </div>
                        )}
                        <p className="border-t border-gray-100 pt-3 text-xs text-gray-400">
                          翻译由 AI 生成，专业术语已尽量对齐，重要信息请以英文原文为准。
                        </p>
                      </div>
                    )}
                  </div>
                )}
                {activeTab === 'qa' && renderTranscriptText(detail.questions_and_answers)}
                {activeTab === 'prepared' && renderTranscriptText(detail.prepared_remarks)}
                {activeTab === 'segments' && (
                  <div className="space-y-3">
                    {[...preparedSegments, ...qaSegments].map((segment, index) => (
                      <article
                        key={`${segment.section}-${segment.speaker ?? 'unknown'}-${index}`}
                        className="rounded-lg border border-gray-200 bg-gray-50 p-4"
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <span className="text-sm font-bold text-gray-900">{segment.speaker ?? 'Unknown'}</span>
                          <span
                            className={`rounded-md px-2 py-1 text-xs font-bold ${
                              segment.section === 'questions_and_answers'
                                ? 'bg-emerald-100 text-emerald-700'
                                : 'bg-blue-100 text-blue-700'
                            }`}
                          >
                            {segment.section === 'questions_and_answers' ? 'Q&A' : 'Prepared'}
                          </span>
                        </div>
                        {renderTranscriptText(segment.text)}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
      </div>
    </DashboardShell>
  )
}
