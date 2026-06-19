'use client'

import { useState } from 'react'
import { Upload, X, Check, Loader2 } from 'lucide-react'
import { supplyChainApi, type DocumentType } from '@/lib/api/supply_chain'

const DOC_TYPES: { value: DocumentType; label: string }[] = [
  { value: '10-K', label: 'SEC 10-K（年报）' },
  { value: '10-Q', label: 'SEC 10-Q（季报）' },
  { value: '8-K', label: 'SEC 8-K（重大事件）' },
  { value: 'earnings_call', label: '电话会议记录' },
  { value: 'investor_relations', label: '投资者关系资料' },
]

interface IngestPanelProps {
  onSuccess?: () => void
}

export default function IngestPanel({ onSuccess }: IngestPanelProps) {
  const [url, setUrl] = useState('')
  const [docType, setDocType] = useState<DocumentType>('10-K')
  const [ticker, setTicker] = useState('')
  const [periodStr, setPeriodStr] = useState('')
  const [section, setSection] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)

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
      setTicker('')
      setPeriodStr('')
      setSection('')
      onSuccess?.()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '提交失败，请检查 URL 是否正确'
      setResult({ success: false, message: msg })
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
          <label className="text-xs font-medium text-gray-600 block mb-1">报告期（可选）</label>
          <input
            type="date"
            value={periodStr}
            onChange={(e) => setPeriodStr(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">章节（可选）</label>
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
          {result.success ? <Check className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> : <X className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
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
