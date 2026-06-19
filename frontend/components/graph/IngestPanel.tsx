'use client'

import { useState } from 'react'
import { Upload, X, Check, Loader2, Zap, Search, ClipboardPaste } from 'lucide-react'
import { supplyChainApi, type DocumentType } from '@/lib/api/supply_chain'
import apiClient from '@/lib/api/client'

// ── 类型 ────────────────────────────────────────
type Mode = 'quick' | 'url' | 'paste'

const DOC_TYPES: { value: DocumentType; label: string }[] = [
  { value: '10-K', label: 'SEC 10-K（年报）' },
  { value: '10-Q', label: 'SEC 10-Q（季报）' },
  { value: '8-K', label: 'SEC 8-K（重大事件）' },
  { value: 'earnings_call', label: '电话会议记录' },
  { value: 'investor_relations', label: '投资者关系资料' },
]

const QUICK_TICKERS = ['NVDA', 'TSMC', 'MU', 'MSFT', 'META', 'VRT', 'AVGO', 'AMD']

interface Result {
  success: boolean
  message: string
}

interface IngestPanelProps {
  onSuccess?: () => void
}

// ── 快捷摄取（按股票代码） ───────────────────────
function QuickIngest({ onSuccess }: IngestPanelProps) {
  const [ticker, setTicker] = useState('NVDA')
  const [secForm, setSecForm] = useState('10-K')
  const [ecYear, setEcYear] = useState(new Date().getFullYear())
  const [ecQuarter, setEcQuarter] = useState(Math.ceil((new Date().getMonth() + 1) / 3))
  const [loadingSec, setLoadingSec] = useState(false)
  const [loadingEc, setLoadingEc] = useState(false)
  const [result, setResult] = useState<Result | null>(null)

  const showResult = (r: Result) => {
    setResult(r)
    if (r.success) setTimeout(() => setResult(null), 4000)
  }

  const handleSecIngest = async () => {
    setLoadingSec(true)
    setResult(null)
    try {
      const { data } = await apiClient.post(
        `/api/v1/supply-chain/ingest/sec`,
        null,
        { params: { ticker, form_type: secForm } },
      )
      showResult({ success: true, message: data.message })
      onSuccess?.()
    } catch (e: unknown) {
      showResult({ success: false, message: e instanceof Error ? e.message : '提交失败' })
    } finally {
      setLoadingSec(false)
    }
  }

  const handleEcIngest = async () => {
    setLoadingEc(true)
    setResult(null)
    try {
      const { data } = await apiClient.post(
        `/api/v1/supply-chain/ingest/earnings-call`,
        null,
        { params: { ticker, year: ecYear, quarter: ecQuarter } },
      )
      showResult({ success: true, message: data.message })
      onSuccess?.()
    } catch (e: unknown) {
      showResult({ success: false, message: e instanceof Error ? e.message : '提交失败' })
    } finally {
      setLoadingEc(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* 股票代码选择 */}
      <div>
        <label className="text-xs font-medium text-gray-600 block mb-1.5">股票代码</label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {QUICK_TICKERS.map((t) => (
            <button
              key={t}
              onClick={() => setTicker(t)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                ticker === t
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-blue-300'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="或手动输入..."
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="border-t border-gray-100 pt-4 space-y-3">
        {/* SEC 文件摄取 */}
        <div className="bg-blue-50 rounded-xl p-3 space-y-2">
          <p className="text-xs font-semibold text-blue-800 flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5" />
            SEC 文件（自动查最新版）
          </p>
          <div className="flex gap-2">
            <select
              value={secForm}
              onChange={(e) => setSecForm(e.target.value)}
              className="flex-1 text-xs border border-blue-200 bg-white rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="10-K">10-K 年报</option>
              <option value="10-Q">10-Q 季报</option>
              <option value="8-K">8-K 重大事件</option>
            </select>
            <button
              onClick={handleSecIngest}
              disabled={loadingSec || !ticker}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white text-xs font-medium rounded-lg transition-colors"
            >
              {loadingSec ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              摄取
            </button>
          </div>
        </div>

        {/* 电话会议摄取 */}
        <div className="bg-purple-50 rounded-xl p-3 space-y-2">
          <p className="text-xs font-semibold text-purple-800 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5" />
            电话会议记录（FMP）
          </p>
          <div className="flex gap-2">
            <select
              value={ecYear}
              onChange={(e) => setEcYear(Number(e.target.value))}
              className="flex-1 text-xs border border-purple-200 bg-white rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-purple-500"
            >
              {[2025, 2024, 2023, 2022].map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <select
              value={ecQuarter}
              onChange={(e) => setEcQuarter(Number(e.target.value))}
              className="w-20 text-xs border border-purple-200 bg-white rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-purple-500"
            >
              <option value={1}>Q1</option>
              <option value={2}>Q2</option>
              <option value={3}>Q3</option>
              <option value={4}>Q4</option>
            </select>
            <button
              onClick={handleEcIngest}
              disabled={loadingEc || !ticker}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 text-white text-xs font-medium rounded-lg transition-colors"
            >
              {loadingEc ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              摄取
            </button>
          </div>
        </div>
      </div>

      {result && (
        <div
          className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
            result.success
              ? 'bg-green-50 border border-green-200 text-green-700'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {result.success
            ? <Check className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            : <X className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
          <span>{result.message}</span>
        </div>
      )}
    </div>
  )
}

// ── 手动 URL 摄取 ──────────────────────────────
function UrlIngest({ onSuccess }: IngestPanelProps) {
  const [url, setUrl] = useState('')
  const [docType, setDocType] = useState<DocumentType>('10-K')
  const [ticker, setTicker] = useState('')
  const [periodStr, setPeriodStr] = useState('')
  const [section, setSection] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Result | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const res = await supplyChainApi.ingestDocument({
        url: url.trim(),
        document_type: docType,
        ticker: ticker.trim() || undefined,
        period_of_report: periodStr || undefined,
        section: section.trim() || undefined,
      })
      setResult({ success: true, message: res.message })
      setUrl('')
      onSuccess?.()
    } catch (e: unknown) {
      setResult({ success: false, message: e instanceof Error ? e.message : '提交失败' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="text-xs font-medium text-gray-600 block mb-1">文档 URL *</label>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.sec.gov/Archives/..."
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">文档类型 *</label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocumentType)}
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">股票代码</label>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="NVDA"
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">报告期</label>
          <input
            type="date"
            value={periodStr}
            onChange={(e) => setPeriodStr(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">章节</label>
          <input
            type="text"
            value={section}
            onChange={(e) => setSection(e.target.value)}
            placeholder="Risk Factors"
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
      {result && (
        <div
          className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
            result.success
              ? 'bg-green-50 border border-green-200 text-green-700'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {result.success
            ? <Check className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            : <X className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
          <span>{result.message}</span>
        </div>
      )}
      <button
        type="submit"
        disabled={loading || !url.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg transition-colors"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
        {loading ? '处理中…' : '提交摄取'}
      </button>
    </form>
  )
}

// ── 粘贴文本摄取 ──────────────────────────────
function PasteIngest({ onSuccess }: IngestPanelProps) {
  const [text, setText] = useState('')
  const [docType, setDocType] = useState<DocumentType>('earnings_call')
  const [ticker, setTicker] = useState('')
  const [periodStr, setPeriodStr] = useState('')
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Result | null>(null)

  const charCount = text.length
  const isValid = charCount >= 100

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isValid) return
    setLoading(true)
    setResult(null)
    try {
      const res = await supplyChainApi.ingestText({
        text: text.trim(),
        document_type: docType,
        ticker: ticker.trim() || undefined,
        period_of_report: periodStr || undefined,
        title: title.trim() || undefined,
      })
      setResult({ success: true, message: res.message })
      setText('')
      onSuccess?.()
    } catch (e: unknown) {
      setResult({ success: false, message: e instanceof Error ? e.message : '提交失败' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
        从 Seeking Alpha、公司 IR 官网等处复制电话会议记录文本，直接粘贴到下方。
        无需 FMP 权限。
      </div>
      <div>
        <label className="text-xs font-medium text-gray-600 block mb-1">
          文本内容 * <span className={`ml-1 ${isValid ? 'text-green-600' : 'text-gray-400'}`}>({charCount} 字符{isValid ? '' : '，需至少 100 字符'})</span>
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="粘贴电话会议记录、投资者关系材料或其他文本..."
          rows={8}
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y font-mono"
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">文档类型 *</label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocumentType)}
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">股票代码</label>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="NVDA"
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">报告期</label>
          <input
            type="date"
            value={periodStr}
            onChange={(e) => setPeriodStr(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">标题（可选）</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="NVDA Q3 2024 Earnings Call"
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
      {result && (
        <div
          className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
            result.success
              ? 'bg-green-50 border border-green-200 text-green-700'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {result.success
            ? <Check className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            : <X className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
          <span>{result.message}</span>
        </div>
      )}
      <button
        type="submit"
        disabled={loading || !isValid}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-xs font-medium rounded-lg transition-colors"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ClipboardPaste className="w-3.5 h-3.5" />}
        {loading ? '处理中…' : '提交文本'}
      </button>
    </form>
  )
}

// ── 主组件（Tab 切换） ──────────────────────────
export default function IngestPanel({ onSuccess }: IngestPanelProps) {
  const [mode, setMode] = useState<Mode>('quick')

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-gray-100 pb-2 flex-wrap">
        <button
          onClick={() => setMode('quick')}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            mode === 'quick'
              ? 'bg-blue-50 text-blue-700 border border-blue-200'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Zap className="w-3 h-3 inline mr-1" />
          快捷摄取
        </button>
        <button
          onClick={() => setMode('url')}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            mode === 'url'
              ? 'bg-blue-50 text-blue-700 border border-blue-200'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <Upload className="w-3 h-3 inline mr-1" />
          手动 URL
        </button>
        <button
          onClick={() => setMode('paste')}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            mode === 'paste'
              ? 'bg-amber-50 text-amber-700 border border-amber-200'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          <ClipboardPaste className="w-3 h-3 inline mr-1" />
          粘贴文本
        </button>
      </div>

      {mode === 'quick' && <QuickIngest onSuccess={onSuccess} />}
      {mode === 'url' && <UrlIngest onSuccess={onSuccess} />}
      {mode === 'paste' && <PasteIngest onSuccess={onSuccess} />}
    </div>
  )
}
