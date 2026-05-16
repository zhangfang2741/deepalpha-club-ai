'use client'

import { useEffect, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
} from 'lightweight-charts'
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import {
  FlaskConical,
  Send,
  X,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Loader2,
} from 'lucide-react'
import {
  type FactorPoint,
  type Freq,
  type KlineBar,
  type SkillMessage,
  fetchKline,
  generateSkillStream,
  runSkill,
} from '@/lib/api/skills'
import DashboardShell from '@/components/layout/DashboardShell'

// ─── 类型 ─────────────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant'
  content: string
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const TEMPLATES = [
  {
    label: '⚡ 动量',
    prompt: '帮我创建一个动量因子，计算过去3个月（跳过最近1个月）的价格涨幅，并对结果做标准化处理。',
  },
  {
    label: '📊 均线偏离',
    prompt: '创建一个技术分析因子：收盘价相对于20日均线的偏离程度，数值越高代表超买状态。',
  },
  {
    label: '💰 波动率',
    prompt: '生成一个波动率因子，计算过去60天的日收益率标准差，用来衡量价格波动风险。',
  },
  {
    label: '🛡️ 趋势强度',
    prompt: '创建一个趋势强度因子：统计过去20天中收盘价高于前日的天数占比，代表价格上涨概率。',
  },
  {
    label: '🎯 RSI',
    prompt: '实现14日 RSI（相对强弱指标），高值（>70）代表超买，低值（<30）代表超卖。',
  },
  {
    label: '🚀 成交量动能',
    prompt: '构建一个成交量加权动量因子：以成交量为权重，计算过去30天的加权价格变化率。',
  },
] as const

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function extractCode(text: string): string {
  const matches = [...text.matchAll(/```python\n([\s\S]*?)```/g)]
  return matches.length ? matches[matches.length - 1][1].trim() : ''
}

function getDisplayText(text: string): string {
  return text.replace(/```(?:python)?\n[\s\S]*?```/g, '').trim()
}

// ─── 图表组件 ─────────────────────────────────────────────────────────────────

interface SkillChartProps {
  klines: KlineBar[]
  factor: FactorPoint[]
  outputType: string
  symbol: string
  isRunning: boolean
}

function SkillChart({ klines, factor, outputType, symbol, isRunning }: SkillChartProps) {
  const mainRef = useRef<HTMLDivElement>(null)
  const subRef = useRef<HTMLDivElement>(null)
  const mainChartRef = useRef<IChartApi | null>(null)
  const subChartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const factorMapRef = useRef<Map<string, number>>(new Map())
  const syncingRef = useRef(false)

  // 初始化图表（只执行一次）
  useEffect(() => {
    if (!mainRef.current || !subRef.current) return

    const chartBase = {
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      autoSize: true,
    }

    const mainChart = createChart(mainRef.current, {
      ...chartBase,
      timeScale: { timeVisible: true, borderColor: '#374151' },
      rightPriceScale: { borderColor: '#374151' },
    })

    const subChart = createChart(subRef.current, {
      ...chartBase,
      timeScale: { visible: false, borderColor: '#374151' },
      rightPriceScale: { borderColor: '#374151' },
    })

    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    const lineSeries = subChart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
    })

    // Crosshair 联动
    mainChart.subscribeCrosshairMove((param) => {
      if (!lineSeriesRef.current || !subChartRef.current) return
      if (!param.time) {
        subChartRef.current.clearCrosshairPosition()
        return
      }
      const val = factorMapRef.current.get(param.time as string) ?? 0
      subChartRef.current.setCrosshairPosition(val, param.time as Time, lineSeriesRef.current)
    })

    // 时间轴双向同步
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (syncingRef.current || !range) return
      syncingRef.current = true
      subChart.timeScale().setVisibleLogicalRange(range)
      syncingRef.current = false
    })
    subChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (syncingRef.current || !range) return
      syncingRef.current = true
      mainChart.timeScale().setVisibleLogicalRange(range)
      syncingRef.current = false
    })

    mainChartRef.current = mainChart
    subChartRef.current = subChart
    candleSeriesRef.current = candleSeries
    lineSeriesRef.current = lineSeries

    return () => {
      mainChart.remove()
      subChart.remove()
    }
  }, [])

  // 更新 K 线数据
  useEffect(() => {
    if (!candleSeriesRef.current || !klines.length) return
    const data = klines.map((k) => ({
      time: k.time as Time,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }))
    candleSeriesRef.current.setData(data)
    mainChartRef.current?.timeScale().fitContent()
  }, [klines])

  // 更新因子数据
  useEffect(() => {
    if (!lineSeriesRef.current || !factor.length) return
    const map = new Map<string, number>()
    const data = factor.map((f) => {
      map.set(f.time, f.value)
      return { time: f.time as Time, value: f.value }
    })
    factorMapRef.current = map
    lineSeriesRef.current.setData(data)
  }, [factor])

  const label = outputType === 'signal' ? '信号' : outputType === 'risk' ? '风险' : '因子分'

  return (
    <div className="flex flex-col h-full">
      {/* K 线主图 */}
      <div className="flex-[65] min-h-0 relative">
        <div className="absolute top-2 left-3 text-xs text-gray-400 z-10 pointer-events-none">
          {symbol} · K 线
        </div>
        <div ref={mainRef} className="h-full w-full" />
      </div>

      {/* 因子副图 */}
      <div className="flex-[35] min-h-0 flex flex-col border-t border-gray-700">
        <div className="flex items-center justify-between px-3 py-1 bg-gray-800 text-xs text-gray-400 flex-shrink-0">
          <span>{label}</span>
          {isRunning && (
            <span className="flex items-center gap-1 text-blue-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              计算中...
            </span>
          )}
        </div>
        <div ref={subRef} className="flex-1 min-h-0" />
      </div>
    </div>
  )
}

// ─── 主页面 ───────────────────────────────────────────────────────────────────

export default function FactorExplorerPage() {
  // 环境设置
  const [symbol, setSymbol] = useState('600519')
  const [startDate, setStartDate] = useState('2023-01-01')
  const [endDate, setEndDate] = useState('2026-05-01')
  const [freq, setFreq] = useState<Freq>('daily')

  // 数据状态
  const [klines, setKlines] = useState<KlineBar[]>([])
  const [factor, setFactor] = useState<FactorPoint[]>([])
  const [outputType, setOutputType] = useState('factor')
  const [dataReady, setDataReady] = useState(false)
  const [loadingKline, setLoadingKline] = useState(false)

  // 对话状态
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentCode, setCurrentCode] = useState('')
  const [runningSkill, setRunningSkill] = useState(false)

  // UI 状态
  const [showCode, setShowCode] = useState(false)
  const [published, setPublished] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [runError, setRunError] = useState('')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── 加载 K 线数据 ──────────────────────────────────────────────────────────

  const handleLoadKline = async () => {
    if (!symbol.trim()) return
    setLoadingKline(true)
    setLoadError('')
    setDataReady(false)
    setFactor([])
    setCurrentCode('')
    setMessages([])
    setPublished(false)
    try {
      const resp = await fetchKline(symbol.trim().toUpperCase(), startDate, endDate, freq)
      setKlines(resp.klines)
      setDataReady(true)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : '加载失败，请检查股票代码')
    } finally {
      setLoadingKline(false)
    }
  }

  // ── 发送消息 ───────────────────────────────────────────────────────────────

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading || !dataReady) return

    const userMsg: Message = { role: 'user', content: text }
    const historyForApi: SkillMessage[] = [...messages, userMsg].map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
    }))

    const assistantIdx = messages.length + 1
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '' }])
    setInput('')
    setLoading(true)
    setRunError('')

    abortRef.current = new AbortController()
    let accumulated = ''

    try {
      await generateSkillStream(
        historyForApi,
        (chunk) => {
          accumulated += chunk
          const display = getDisplayText(accumulated)
          setMessages((prev) => {
            const updated = [...prev]
            updated[assistantIdx] = { role: 'assistant', content: display || accumulated }
            return updated
          })
        },
        async () => {
          setLoading(false)
          const code = extractCode(accumulated)
          if (!code) return
          setCurrentCode(code)
          setRunningSkill(true)
          try {
            const result = await runSkill(code, symbol.trim().toUpperCase(), startDate, endDate, freq)
            setFactor(result.factor)
            setOutputType(result.output_type)
          } catch (e) {
            setRunError(e instanceof Error ? e.message : '因子计算失败')
          } finally {
            setRunningSkill(false)
          }
        },
        abortRef.current.signal,
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        const errMsg = e instanceof Error ? e.message : '请求失败，请重试'
        setMessages((prev) => {
          const updated = [...prev]
          updated[assistantIdx] = { role: 'assistant', content: `⚠️ ${errMsg}` }
          return updated
        })
      }
      setLoading(false)
    }
  }

  const handleAbort = () => {
    abortRef.current?.abort()
    setLoading(false)
  }

  const handleTemplateClick = (prompt: string) => {
    setInput(prompt)
  }

  const handlePublish = () => setPublished(true)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ─── 渲染 ──────────────────────────────────────────────────────────────────

  return (
    <DashboardShell>
      <div className="-mx-6 -my-8 flex flex-col overflow-hidden bg-gray-950 h-full">

      {/* ── 环境准备区（横向滚动，所有控件单行） ──────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-gray-900 border-b border-gray-700 flex-shrink-0 overflow-x-auto">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <FlaskConical className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-white whitespace-nowrap">因子探索</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <label className="text-xs text-gray-400 whitespace-nowrap">股票</label>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLoadKline()}
            placeholder="600519"
            className="w-20 h-8 px-2 text-sm bg-gray-800 border border-gray-600 rounded text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <label className="text-xs text-gray-400 whitespace-nowrap">开始</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-8 px-2 text-sm bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <label className="text-xs text-gray-400 whitespace-nowrap">结束</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-8 px-2 text-sm bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <label className="text-xs text-gray-400 whitespace-nowrap">粒度</label>
          <select
            value={freq}
            onChange={(e) => setFreq(e.target.value as Freq)}
            className="h-8 px-2 text-sm bg-gray-800 border border-gray-600 rounded text-white focus:outline-none focus:border-blue-500"
          >
            <option value="daily">日线</option>
            <option value="weekly">周线</option>
          </select>
        </div>
        <button
          onClick={handleLoadKline}
          disabled={loadingKline}
          className="h-8 px-4 text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded transition-colors flex items-center gap-1.5 flex-shrink-0 whitespace-nowrap"
        >
          {loadingKline ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin" />加载中</>
          ) : (
            '▶ 加载数据'
          )}
        </button>
        {loadError && (
          <span className="text-xs text-red-400 whitespace-nowrap flex-shrink-0">{loadError}</span>
        )}
        {dataReady && !loadingKline && (
          <span className="text-xs text-green-400 flex items-center gap-1 flex-shrink-0 whitespace-nowrap">
            <CheckCircle2 className="w-3 h-3" />{symbol.toUpperCase()} 就绪
          </span>
        )}
      </div>

      {/* ── 主内容区 ──────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 divide-x divide-gray-700">

        {/* ── 左侧：对话区 ──────────────────────────────────────────────── */}
        <div className="w-[40%] min-w-[220px] flex flex-col min-h-0 bg-gray-900">

          {/* 快速模板 */}
          {dataReady && (
            <div className="flex gap-1.5 flex-wrap px-3 py-2 border-b border-gray-700 flex-shrink-0">
              {TEMPLATES.map((t) => (
                <button
                  key={t.label}
                  onClick={() => handleTemplateClick(t.prompt)}
                  disabled={loading}
                  className="text-xs px-2.5 py-1 rounded-full bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-600 transition-colors disabled:opacity-50"
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}

          {/* 消息区 */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {!dataReady ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500 text-sm text-center gap-3">
                <FlaskConical className="w-10 h-10 text-gray-700" />
                <div>
                  <p className="font-medium text-gray-400">开始因子探索</p>
                  <p className="text-xs mt-1">在顶部输入股票代码并加载数据，<br />然后描述你的因子思路</p>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500 text-sm text-center gap-3">
                <div className="w-12 h-12 rounded-full bg-blue-900/50 flex items-center justify-center">
                  <FlaskConical className="w-6 h-6 text-blue-400" />
                </div>
                <div>
                  <p className="font-medium text-gray-300">{symbol.toUpperCase()} 数据已就绪</p>
                  <p className="text-xs mt-1 text-gray-500">选择快速模板或描述你的因子分析思路</p>
                </div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-br-sm'
                        : 'bg-gray-800 text-gray-200 rounded-bl-sm'
                    }`}
                  >
                    {msg.content || (
                      <span className="flex gap-1 items-center">
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 输入区 */}
          <div className="border-t border-gray-700 p-3 flex-shrink-0 bg-gray-900">
            {runError && (
              <p className="text-xs text-red-400 mb-2">⚠️ {runError}</p>
            )}
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!dataReady || loading}
                placeholder={dataReady ? '描述你的因子分析思路，或点击上方快速模板...' : '请先加载股票数据'}
                rows={3}
                className="flex-1 resize-none px-3 py-2 text-sm bg-gray-800 border border-gray-600 rounded-xl text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
              <button
                onClick={loading ? handleAbort : handleSend}
                disabled={!dataReady || (!loading && !input.trim())}
                className={`w-10 flex-shrink-0 rounded-xl flex items-center justify-center transition-colors ${
                  loading
                    ? 'bg-red-600 hover:bg-red-500 text-white'
                    : 'bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white disabled:text-gray-500'
                }`}
              >
                {loading ? <X className="w-4 h-4" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>

        {/* ── 右侧：图表区 ──────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
          {!dataReady ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-600">
                <FlaskConical className="w-16 h-16 mx-auto mb-4 text-gray-700" />
                <p className="text-sm">加载股票数据后，K 线图将显示在这里</p>
                <p className="text-xs mt-1 text-gray-700">描述因子后，副图会自动展示计算结果</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 min-h-0">
              <SkillChart
                klines={klines}
                factor={factor}
                outputType={outputType}
                symbol={symbol}
                isRunning={runningSkill}
              />
            </div>
          )}

          {/* 底部操作栏 */}
          {currentCode && (
            <div className="border-t border-gray-700 px-4 py-2.5 flex items-center justify-between flex-shrink-0 bg-gray-900">
              <button
                onClick={() => setShowCode((v) => !v)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
              >
                {showCode ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
                查看代码
              </button>
              <button
                onClick={handlePublish}
                disabled={published || runningSkill}
                className={`flex items-center gap-2 px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                  published
                    ? 'bg-green-800 text-green-200 cursor-default'
                    : 'bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50'
                }`}
              >
                {published ? (
                  <><CheckCircle2 className="w-4 h-4" />已发布到 Skill 市场</>
                ) : (
                  '📤 发布到 Skill 市场'
                )}
              </button>
            </div>
          )}

          {/* 代码折叠面板（开发者用） */}
          {showCode && currentCode && (
            <div className="border-t border-gray-700 bg-gray-950 max-h-48 overflow-auto flex-shrink-0">
              <pre className="p-4 text-xs text-gray-300 font-mono leading-relaxed whitespace-pre-wrap">
                {currentCode}
              </pre>
            </div>
          )}
        </div>
      </div>
      </div>
    </DashboardShell>
  )
}
