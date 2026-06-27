'use client'

import { useState } from 'react'
import {
  AlertTriangle,
  BookOpen,
  Building2,
  ChevronDown,
  ChevronRight,
  DollarSign,
  GitBranch,
  Lightbulb,
  TrendingUp,
} from 'lucide-react'
import Spinner from '@/components/ui/Spinner'
import type {
  BusinessModelData,
  EvidenceItem,
  IndustryChainData,
  InvestmentViewData,
  KeyBottlenecksData,
  LeadingCompaniesData,
  ResearchStepData,
  UnderstandIndustryData,
  WhyItExistsData,
} from '@/lib/api/research'

const STEP_META = [
  { icon: BookOpen,        color: 'blue'   },
  { icon: Lightbulb,       color: 'yellow' },
  { icon: GitBranch,       color: 'purple' },
  { icon: AlertTriangle,   color: 'orange' },
  { icon: Building2,       color: 'green'  },
  { icon: DollarSign,      color: 'emerald'},
  { icon: TrendingUp,      color: 'indigo' },
] as const

const COLOR_MAP: Record<string, string> = {
  blue:    'border-blue-200 bg-blue-50',
  yellow:  'border-yellow-200 bg-yellow-50',
  purple:  'border-purple-200 bg-purple-50',
  orange:  'border-orange-200 bg-orange-50',
  green:   'border-green-200 bg-green-50',
  emerald: 'border-emerald-200 bg-emerald-50',
  indigo:  'border-indigo-200 bg-indigo-50',
}

const ICON_COLOR_MAP: Record<string, string> = {
  blue:    'text-blue-600 bg-blue-100',
  yellow:  'text-yellow-600 bg-yellow-100',
  purple:  'text-purple-600 bg-purple-100',
  orange:  'text-orange-600 bg-orange-100',
  green:   'text-green-600 bg-green-100',
  emerald: 'text-emerald-600 bg-emerald-100',
  indigo:  'text-indigo-600 bg-indigo-100',
}

function EvidenceBlock({ evidence }: { evidence: EvidenceItem[] }) {
  const [open, setOpen] = useState(false)
  if (!evidence?.length) return null
  return (
    <div className="mt-3 border-t border-gray-100 pt-2">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        证据来源（{evidence.length} 条）
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5">
          {evidence.map((e, i) => (
            <li key={i} className="text-xs text-gray-500 flex gap-2">
              <span className="text-gray-300 flex-shrink-0">·</span>
              <span>
                {e.snippet}
                {e.source.startsWith('http') ? (
                  <a href={e.source} target="_blank" rel="noopener noreferrer"
                    className="ml-1 text-blue-400 underline hover:text-blue-600">来源</a>
                ) : (
                  <span className="ml-1 text-gray-400">（{e.source}）</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function StringList({ items, className }: { items: string[]; className?: string }) {
  return (
    <ul className={`space-y-1 ${className ?? ''}`}>
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm text-gray-700">
          <span className="text-gray-400 flex-shrink-0 mt-0.5">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function WhatWhy({ what, why }: { what: string; why: string }) {
  return (
    <div className="space-y-1 mb-3">
      <p className="text-sm"><span className="font-semibold text-gray-800">是什么：</span>{what}</p>
      <p className="text-sm"><span className="font-semibold text-gray-800">为什么：</span>{why}</p>
    </div>
  )
}

function StepContent({ stepIndex, data }: { stepIndex: number; data: ResearchStepData }) {
  switch (stepIndex) {
    case 0: {
      const d = data as UnderstandIndustryData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <p className="text-sm text-gray-700 mb-3">{d.description}</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">主要产品</p>
              <StringList items={d.main_products} />
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">主要客户</p>
              <StringList items={d.key_customers} />
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2 italic">{d.development_stage}</p>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 1: {
      const d = data as WhyItExistsData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: '技术驱动', items: d.tech_drivers },
              { label: '政策驱动', items: d.policy_drivers },
              { label: '需求驱动', items: d.demand_drivers },
              { label: '成本变化', items: d.cost_drivers },
            ].map(({ label, items }) => (
              <div key={label}>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{label}</p>
                <StringList items={items} />
              </div>
            ))}
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 2: {
      const d = data as IndustryChainData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="grid grid-cols-3 gap-3">
            {[d.upstream, d.midstream, d.downstream].map((chain) => (
              <div key={chain.level} className="bg-white rounded-lg border border-gray-100 p-3">
                <p className="text-xs font-bold text-gray-700 mb-1">{chain.level}</p>
                <p className="text-xs text-gray-500 mb-2">{chain.description}</p>
                <ul className="space-y-0.5">
                  {chain.key_players.map((p, i) => (
                    <li key={i} className="text-xs text-gray-600">· {p}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 3: {
      const d = data as KeyBottlenecksData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="space-y-3">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">核心瓶颈</p>
              <StringList items={d.bottlenecks} />
            </div>
            <div className="bg-orange-50 border border-orange-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-orange-700 mb-0.5">定价权</p>
              <p className="text-sm text-gray-700">{d.pricing_power}</p>
            </div>
            <div className="bg-green-50 border border-green-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-green-700 mb-0.5">最赚钱环节</p>
              <p className="text-sm text-gray-700">{d.most_profitable_segment}</p>
            </div>
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 4: {
      const d = data as LeadingCompaniesData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {d.companies.map((c) => (
              <div key={c.name} className="bg-white border border-gray-100 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-sm text-gray-800">{c.name}</span>
                  {c.ticker && (
                    <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-mono">
                      {c.ticker}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600 mb-1">{c.business}</p>
                <p className="text-xs text-gray-500"><span className="font-medium">护城河：</span>{c.moat}</p>
              </div>
            ))}
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 5: {
      const d = data as BusinessModelData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: '收入模式', value: d.revenue_model },
              { label: '成本结构', value: d.cost_structure },
              { label: '利润驱动', value: d.profit_drivers },
            ].map(({ label, value }) => (
              <div key={label} className="bg-white border border-gray-100 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-500 mb-1">{label}</p>
                <p className="text-sm text-gray-700">{value}</p>
              </div>
            ))}
            <div className="bg-white border border-gray-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-gray-500 mb-1">护城河来源</p>
              <StringList items={d.moat_sources} />
            </div>
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    case 6: {
      const d = data as InvestmentViewData
      return (
        <>
          <WhatWhy what={d.what} why={d.why} />
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="bg-green-50 border border-green-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-green-700 mb-1">投资机会</p>
              <StringList items={d.opportunities} />
            </div>
            <div className="bg-red-50 border border-red-100 rounded-lg p-3">
              <p className="text-xs font-semibold text-red-700 mb-1">主要风险</p>
              <StringList items={d.risks} />
            </div>
          </div>
          <div className="mb-3">
            <p className="text-xs font-semibold text-gray-500 mb-1">重点关注方向</p>
            <StringList items={d.focus_areas} />
          </div>
          <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3">
            <p className="text-xs font-semibold text-indigo-700 mb-1">综合观点</p>
            <p className="text-sm text-gray-700">{d.conclusion}</p>
          </div>
          <EvidenceBlock evidence={d.evidence} />
        </>
      )
    }
    default:
      return null
  }
}

export interface StepState {
  status: 'pending' | 'loading' | 'done' | 'error'
  data?: ResearchStepData
  error?: string
}

interface Props {
  stepIndex: number
  label: string
  state: StepState
}

export default function ResearchStepCard({ stepIndex, label, state }: Props) {
  const meta = STEP_META[stepIndex]
  const Icon = meta.icon
  const color = meta.color

  return (
    <div className={`rounded-xl border p-4 transition-all ${
      state.status === 'pending'
        ? 'border-gray-200 bg-gray-50 opacity-50'
        : state.status === 'loading'
        ? 'border-blue-200 bg-blue-50 shadow-sm'
        : state.status === 'error'
        ? 'border-red-200 bg-red-50'
        : COLOR_MAP[color]
    }`}>
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
          state.status === 'pending' ? 'bg-gray-200 text-gray-400'
          : state.status === 'error' ? 'bg-red-100 text-red-500'
          : ICON_COLOR_MAP[color]
        }`}>
          <Icon className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-400 font-medium">步骤 {stepIndex + 1}/7</p>
          <p className="font-semibold text-gray-800 text-sm">{label}</p>
        </div>
        {state.status === 'loading' && <Spinner className="w-5 h-5 text-blue-500 flex-shrink-0" />}
        {state.status === 'done' && (
          <span className="text-xs text-green-600 font-medium flex-shrink-0">完成</span>
        )}
      </div>

      {state.status === 'loading' && (
        <p className="text-sm text-blue-600 animate-pulse">正在分析中...</p>
      )}

      {state.status === 'error' && (
        <p className="text-sm text-red-600">{state.error ?? '分析失败，跳过此步骤'}</p>
      )}

      {state.status === 'done' && state.data && (
        <StepContent stepIndex={stepIndex} data={state.data} />
      )}
    </div>
  )
}
