'use client'
import { useState } from 'react'
import { saveSkill, generateSkillStream } from '@/lib/api/skills'

const CATEGORIES = [
  { id: 'momentum', label: '强者恒强', desc: '动量/趋势类因子' },
  { id: 'reversal', label: '跌深必反', desc: '均值回归类因子' },
  { id: 'volatility', label: '波动突破', desc: '波动率类因子' },
  { id: 'volume', label: '量价共振', desc: '成交量类因子' },
  { id: 'sentiment', label: '情绪极端', desc: '情绪/RSI 类因子' },
  { id: 'technical', label: '技术指标', desc: '均线/MACD 等技术指标' },
]

function extractCode(text: string): string {
  const matches = [...text.matchAll(/```python\n([\s\S]*?)```/g)]
  return matches.length ? matches[matches.length - 1][1].trim() : text.trim()
}

export function NewView() {
  const [step, setStep] = useState(1)
  const [symbol, setSymbol] = useState('')
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2025-05-16')
  const [freq, setFreq] = useState<'daily' | 'weekly'>('daily')
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [code, setCode] = useState('')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [generatedCode, setGeneratedCode] = useState('')

  const canStep2 = symbol.trim().length > 0 && startDate && endDate

  const handleGenerate = async () => {
    if (!category && !description.trim()) {
      setError('请选择命题类型或输入描述')
      return
    }
    setError(null)
    setGenerating(true)
    setGeneratedCode('')

    const prompt = description.trim() || `请生成一个 ${CATEGORIES.find((c) => c.id === category)?.label || category} 类因子，用于分析 ${symbol}`

    try {
      let fullContent = ''
      await generateSkillStream(
        [{ role: 'user', content: prompt }],
        (chunk) => { fullContent += chunk },
        () => {},
      )
      const extracted = extractCode(fullContent)
      setGeneratedCode(extracted)
      setCode(extracted)
      setStep(3)
    } catch (e) {
      setError('生成失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  const handleSave = async () => {
    if (!code.trim()) return
    try {
      await saveSkill({
        title: `${symbol} · ${category || '自定义'} 因子`,
        description: description || CATEGORIES.find((c) => c.id === category)?.desc || '自定义因子',
        category: category || 'custom',
        code,
        symbol,
        start_date: startDate,
        end_date: endDate,
        freq,
      })
      setSaved(true)
    } catch (e) {
      setError('保存失败')
    }
  }

  if (saved) {
    return (
      <div className="text-center py-20">
        <div className="text-5xl mb-4">🎉</div>
        <h2 className="text-xl font-bold text-gray-900">保存成功！</h2>
        <p className="text-gray-500 mt-2">去「我的因子」查看</p>
        <button
          onClick={() => setSaved(false)}
          className="mt-6 text-sm text-blue-600 hover:underline"
        >
          继续新建
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* 步骤指示 */}
      <div className="flex items-center gap-2 mb-8">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors ${
              step >= s ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-400'
            }`}>{s}</div>
            <span className={`text-sm ${step >= s ? 'text-gray-900' : 'text-gray-400'}`}>
              {s === 1 ? '选股' : s === 2 ? '选命题' : '生成保存'}
            </span>
            {s < 3 && <div className="w-8 h-px bg-gray-200" />}
          </div>
        ))}
      </div>

      {/* Step 1: 选股 */}
      {step === 1 && (
        <div className="space-y-4 bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold">第一步：选择股票</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-500 mb-1">股票代码</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="如 NVDA / 600519"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
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
          </div>
          <button
            disabled={!canStep2}
            onClick={() => setStep(2)}
            className="w-full py-2.5 rounded-lg text-white font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            下一步
          </button>
        </div>
      )}

      {/* Step 2: 选命题 */}
      {step === 2 && (
        <div className="space-y-4 bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold">第二步：选择因子方向</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setCategory(cat.id)}
                className={`p-3 rounded-lg border text-left transition-all ${
                  category === cat.id
                    ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="font-medium text-sm">{cat.label}</div>
                <div className="text-xs text-gray-400 mt-0.5">{cat.desc}</div>
              </button>
            ))}
          </div>
          <div>
            <label className="block text-sm text-gray-500 mb-1">或自由描述（可选）</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="描述你想分析的因子逻辑，例如：'过去 20 天的价格动量变化'"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="flex-1 py-2.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors">
              上一步
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating || (!category && !description.trim())}
              className="flex-1 py-2.5 rounded-lg text-white font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
            >
              {generating ? '生成中...' : '生成因子代码'}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: 结果 */}
      {step === 3 && (
        <div className="space-y-4 bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold">第三步：检查并保存</h2>
          {code ? (
            <>
              <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 text-xs overflow-x-auto max-h-96 overflow-y-auto">{code}</pre>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <div className="flex gap-3">
                <button onClick={() => { setCode(''); setStep(2) }} className="flex-1 py-2.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors">
                  重新生成
                </button>
                <button onClick={handleSave} className="flex-1 py-2.5 rounded-lg text-white font-medium bg-blue-600 hover:bg-blue-700 transition-colors">
                  保存到我的因子
                </button>
              </div>
            </>
          ) : (
            <div className="text-center py-8 text-gray-400">代码生成中...</div>
          )}
        </div>
      )}
    </div>
  )
}