'use client'

import { useRef, useState } from 'react'
import { Search } from 'lucide-react'
import DashboardShell from '@/components/layout/DashboardShell'
import ResearchStepCard, { type StepState } from '@/components/research/ResearchStepCard'
import Spinner from '@/components/ui/Spinner'
import { streamIndustryResearch, type ResearchStepData } from '@/lib/api/research'

const STEP_LABELS = ['理解行业', '存在原因', '产业链', '核心瓶颈', '龙头公司', '商业模式', '投资观点']

function initSteps(): StepState[] {
  return Array(7).fill(null).map(() => ({ status: 'pending' as const }))
}

export default function IndustryResearchPage() {
  const [industry, setIndustry] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [steps, setSteps] = useState<StepState[]>(initSteps())
  const [hasStarted, setHasStarted] = useState(false)
  const [globalError, setGlobalError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const doneCount = steps.filter(s => s.status === 'done' || s.status === 'error').length

  const handleStart = async () => {
    if (!industry.trim() || isStreaming) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    const fresh = initSteps()
    fresh[0] = { status: 'loading' }
    setSteps(fresh)
    setHasStarted(true)
    setIsStreaming(true)
    setGlobalError(null)

    try {
      for await (const event of streamIndustryResearch(industry.trim(), abortRef.current.signal)) {
        if (event.event === 'step') {
          const i = event.step_index
          setSteps(prev => {
            const next = [...prev]
            next[i] = { status: 'done', data: event.data as ResearchStepData }
            if (i + 1 < 7) next[i + 1] = { status: 'loading' }
            return next
          })
        } else if (event.event === 'error') {
          const i = event.step_index
          if (i !== null) {
            setSteps(prev => {
              const next = [...prev]
              next[i] = { status: 'error', error: event.message }
              if (i + 1 < 7) next[i + 1] = { status: 'loading' }
              return next
            })
          }
        }
        // 'done' event: streaming ends naturally
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setGlobalError((e as Error).message ?? '研究请求失败')
      }
    } finally {
      setIsStreaming(false)
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleStart()
  }

  return (
    <DashboardShell>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* 标题 */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">行业研究</h1>
          <p className="text-sm text-gray-500 mt-1">
            输入行业名称，AI 自动完成 7 步结构化研究分析，每步结果实时呈现
          </p>
        </div>

        {/* 输入区 */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={industry}
                onChange={e => setIndustry(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="例如：HBM 内存、新能源汽车、创新药、量子计算..."
                disabled={isStreaming}
                className="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>
            {isStreaming ? (
              <button
                onClick={handleStop}
                className="px-4 py-2.5 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-2"
              >
                停止
              </button>
            ) : (
              <button
                onClick={handleStart}
                disabled={!industry.trim()}
                className="px-4 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed rounded-lg transition-colors flex items-center gap-2"
              >
                开始研究
              </button>
            )}
          </div>
        </div>

        {/* 全局错误 */}
        {globalError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">
            {globalError}
          </div>
        )}

        {/* 进度条 */}
        {hasStarted && (
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${(doneCount / 7) * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 flex-shrink-0 flex items-center gap-1.5">
              {isStreaming && <Spinner className="w-3 h-3" />}
              {doneCount}/7 步
            </span>
          </div>
        )}

        {/* 步骤卡片 */}
        {hasStarted && (
          <div className="space-y-3">
            {steps.map((state, i) => (
              <ResearchStepCard
                key={i}
                stepIndex={i}
                label={STEP_LABELS[i]}
                state={state}
              />
            ))}
          </div>
        )}
      </div>
    </DashboardShell>
  )
}
