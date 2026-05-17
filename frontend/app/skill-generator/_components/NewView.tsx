'use client'
import { useState } from 'react'
import { generateSkillStream, runSkill, saveSkill, fetchKline } from '@/lib/api/skills'
import type { KlineBar, FactorPoint } from '@/lib/api/skills'
import { SymbolAutocomplete } from './SymbolAutocomplete'
import { ChatPanel, type ChatMessage } from './ChatPanel'
import { KlineFactorChart } from './KlineFactorChart'
import { DataHelpModal } from './DataHelpModal'

// LLM 偶尔会把后端的 SSE 帧抄进自己的回复，剥掉这种嵌套
function stripSseWrappers(text: string): string {
  const matches = [...text.matchAll(/data:\s*({[\s\S]*?})\s*(?:\n|$)/g)]
  if (matches.length === 0) return text
  const parts: string[] = []
  for (const m of matches) {
    try {
      const obj = JSON.parse(m[1])
      if (typeof obj.content === 'string') parts.push(obj.content)
    } catch { /* 忽略 */ }
  }
  const merged = parts.join('')
  return /data:\s*{/.test(merged) ? stripSseWrappers(merged) : merged
}

function extractCode(text: string): string {
  const cleaned = stripSseWrappers(text)
  const blocks = [...cleaned.matchAll(/```(?:python)?\s*\n?([\s\S]*?)```/g)]
  const withCompute = blocks.find((m) => /\bdef\s+compute\s*\(/.test(m[1]))
  if (withCompute) return withCompute[1].trim()
  if (blocks.length > 0) return blocks[0][1].trim()
  const idx = cleaned.search(/\bdef\s+compute\s*\(/)
  if (idx >= 0) return cleaned.slice(idx).trim()
  return ''
}

// 把后端技术错误翻译成人话
function humanizeRunError(detail: string): string {
  if (!detail) return '这次没能生成可用的因子，请换种说法再试一次。'
  // 因子计算返回空（AI 可能生成了代码但数据不支持，尝试返回了空）
  if (/空结果|返回.*条|compute returned/.test(detail)) {
    return 'AI 生成的因子无法计算（所请求的数据在当前不可用）。请尝试基于 K 线价格、成交量、财务报表（收入/利润/ROE）、分析师预测上调等数据描述因子。'
  }
  // K 线数据问题
  if (/K\s*线|kline|无法获取股票数据/i.test(detail)) {
    return '股票数据加载失败，请检查代码、日期范围或换一只股票。'
  }
  // 沙箱安全 / 语法 / 字段错误 → 代码 bug，建议重述
  if (/Traceback|KeyError|NameError|TypeError|AttributeError|ValueError|IndexError|ZeroDivisionError|sandbox|超时|timeout/i.test(detail)) {
    return 'AI 这次写的代码有点小问题，请把需求说得更具体一点再试一次（比如指明窗口期、阈值）。'
  }
  // 数据点不足
  if (/有效数据点不足|至少\s*\d+\s*个/.test(detail)) {
    return '这次因子能用的数据点太少，请把时间范围拉长，或换一个不同的逻辑。'
  }
  return '这次没能跑出有效的因子，请换种说法再试一次。'
}

const PRESET_RANGES: Array<{ label: string; days: number }> = [
  { label: '1月', days: 30 },
  { label: '半年', days: 183 },
  { label: '1年', days: 365 },
  { label: '3年', days: 365 * 3 },
  { label: '5年', days: 365 * 5 },
]

// 给用户看的纯文字：剥掉 SSE 包装和代码块
function stripCodeForChat(text: string): string {
  return stripSseWrappers(text)
    .replace(/```(?:python)?\s*\n?[\s\S]*?```/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function NewView() {
  // 选股表单
  const [stage, setStage] = useState<'select' | 'workbench'>('select')
  const [symbol, setSymbol] = useState('')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2025-05-16')
  const [freq, setFreq] = useState<'daily' | 'weekly'>('daily')

  // 工作台状态
  const [klines, setKlines] = useState<KlineBar[]>([])
  const [klineLoading, setKlineLoading] = useState(false)
  const [factor, setFactor] = useState<FactorPoint[]>([])
  const [factorLoading, setFactorLoading] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingText, setStreamingText] = useState('')
  const [generating, setGenerating] = useState(false)
  const [latestCode, setLatestCode] = useState('')
  const [latestDesc, setLatestDesc] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const canEnter = symbol.trim().length > 0 && startDate && endDate

  const applyRange = (days: number) => {
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    const today = new Date()
    const start = new Date(today.getTime() - days * 86400000)
    setEndDate(fmt(today))
    setStartDate(fmt(start))
  }

  const reloadKlines = async (days: number) => {
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    const today = new Date()
    const start = new Date(today.getTime() - days * 86400000)
    setEndDate(fmt(today))
    setStartDate(fmt(start))
    setFactor([])
    setFactorLoading(true)
    try {
      const data = await fetchKline(symbol, fmt(start), fmt(today), freq)
      setKlines(data.klines)
    } catch {
      setError('K 线加载失败')
    } finally {
      setFactorLoading(false)
    }
  }

  const enterWorkbench = async () => {
    if (!canEnter) return
    setStage('workbench')
    setError(null)
    setKlineLoading(true)
    try {
      const data = await fetchKline(symbol, startDate, endDate, freq)
      setKlines(data.klines)
    } catch (e) {
      setError('K 线数据加载失败，请检查 symbol 或日期范围')
    } finally {
      setKlineLoading(false)
    }
  }

  const handleSubmit = async (userText: string) => {
    setMessages((prev) => [...prev, { role: 'user', text: userText }])
    setStreamingText('')
    setGenerating(true)
    setFactorLoading(true)
    setError(null)

    // 把已有用户描述串起来作为多轮上下文
    const llmMessages: { role: 'user' | 'assistant'; content: string }[] = []
    for (const m of messages) {
      if (m.role === 'user') llmMessages.push({ role: 'user', content: m.text })
    }
    llmMessages.push({ role: 'user', content: userText })

    let fullContent = ''
    try {
      await generateSkillStream(
        llmMessages,
        (chunk) => {
          fullContent += chunk
          setStreamingText(stripCodeForChat(fullContent))
        },
        () => {},
      )

      const code = extractCode(fullContent)
      if (!code || !/\bdef\s+compute\s*\(/.test(code)) {
        const assistantText = stripCodeForChat(fullContent) || '抱歉，这次没能生成可执行的因子代码，请换种说法再试一次。'
        setMessages((prev) => [...prev, { role: 'assistant', text: assistantText }])
        setError('AI 生成的代码不完整，已忽略这一轮')
        return
      }

      const run = await runSkill(code, symbol, startDate, endDate, freq, {
        include_financials: true,
        include_news: false,
      })
      setFactor(run.factor)
      setLatestCode(code)
      setLatestDesc(userText)

      const assistantText = stripCodeForChat(fullContent) || '已生成因子，请看右侧副图。'
      setMessages((prev) => [...prev, { role: 'assistant', text: assistantText }])
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        ?? (e as { message?: string })?.message
        ?? ''
      // 把技术错误（traceback / KeyError / module not found 等）翻译成人话
      const friendly = humanizeRunError(typeof detail === 'string' ? detail : '')
      setMessages((prev) => [...prev, { role: 'assistant', text: friendly }])
      setError(friendly)
      // 把原始错误打到 console，方便开发者排查
      console.error('[skill-generator] run failed:', detail)
    } finally {
      setStreamingText('')
      setGenerating(false)
      setFactorLoading(false)
    }
  }

  const handleSave = async () => {
    if (!latestCode || !latestDesc) return
    setSaving(true)
    setError(null)
    try {
      await saveSkill({
        title: `${symbol} · ${latestDesc.slice(0, 24)}`,
        description: latestDesc,
        category: 'custom',
        code: latestCode,
        symbol,
        start_date: startDate,
        end_date: endDate,
        freq,
      })
      setSaved(true)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '保存失败'
      setError(typeof detail === 'string' ? detail : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (saved) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4">🎉</div>
        <h2 className="text-xl font-bold text-gray-900">保存成功！</h2>
        <p className="text-gray-500 mt-2">去「我的因子」查看</p>
        <button
          onClick={() => {
            setSaved(false)
            setStage('select')
            setMessages([])
            setFactor([])
            setKlines([])
            setLatestCode('')
            setLatestDesc('')
            setSymbol('')
          }}
          className="mt-6 text-sm text-blue-600 hover:underline"
        >
          继续新建
        </button>
      </div>
    )
  }

  if (stage === 'select') {
    return (
      <div className="max-w-xl mx-auto">
        <div className="space-y-4 bg-white border border-gray-200 rounded-xl p-6">
          <div>
            <h2 className="text-lg font-semibold">选择股票</h2>
            <p className="text-xs text-gray-500 mt-1">选完后进入因子工作台，与 AI 实时共创</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-500 mb-1">股票代码</label>
              <SymbolAutocomplete value={symbol} onChange={setSymbol} />
            </div>
            <div>
              <label className="block text-sm text-gray-500 mb-1">频率</label>
              <select
                value={freq}
                onChange={(e) => setFreq(e.target.value as 'daily' | 'weekly')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="daily">日线</option>
                <option value="weekly">周线</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-500 mb-1">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-500 mb-1">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="col-span-2 flex items-center gap-2 flex-wrap">
              <span className="text-xs text-gray-400">快捷区间：</span>
              {PRESET_RANGES.map((r) => (
                <button
                  key={r.label}
                  type="button"
                  onClick={() => applyRange(r.days)}
                  className="text-xs px-2.5 py-1 rounded-md border border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            disabled={!canEnter}
            onClick={enterWorkbench}
            className="w-full py-2.5 rounded-lg text-white font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            开始 →
          </button>
        </div>
      </div>
    )
  }

  // 工作台
  return (
    <div className="-mx-6 -my-6 h-[calc(100%+3rem)] flex flex-col bg-gray-50">
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setStage('select')}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            ← 换一只股票
          </button>
          <span className="text-sm font-mono font-semibold text-gray-900">{symbol}</span>
          <span className="text-xs text-gray-400">
            {startDate} ~ {endDate} · {freq === 'daily' ? '日线' : '周线'}
          </span>
          <div className="flex items-center gap-1 ml-2">
            {PRESET_RANGES.map((r) => (
              <button
                key={r.label}
                type="button"
                onClick={() => reloadKlines(r.days)}
                className="text-xs px-2 py-0.5 rounded border border-gray-200 text-gray-500 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={!latestCode || saving}
          className="px-4 py-1.5 rounded-lg text-white text-sm font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? '保存中…' : '保存到我的因子'}
        </button>
        <DataHelpModal />
      </div>

      {error && (
        <div className="px-4 py-1.5 bg-red-50 text-red-700 text-xs border-b border-red-100">{error}</div>
      )}

      <div className="flex-1 min-h-0 flex">
        <div className="w-[40%] min-w-[320px] max-w-[500px] border-r border-gray-200">
          <ChatPanel
            messages={messages}
            streamingText={streamingText}
            generating={generating}
            onSubmit={handleSubmit}
          />
        </div>
        <div className="flex-1 min-w-0 p-3">
          <KlineFactorChart
            klines={klines}
            factor={factor}
            klineLoading={klineLoading}
            factorLoading={factorLoading}
            emptyHint="在左侧描述你想要的因子，副图会实时显示"
          />
        </div>
      </div>
    </div>
  )
}
