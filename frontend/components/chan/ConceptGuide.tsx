'use client'
import { useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'
import { CHAN_TERMS } from '@/lib/chan-glossary'

// 顶部可折叠的「缠论概念速览」：一次看懂所有核心术语，给不熟悉缠论的用户做科普
export function ConceptGuide() {
  const [open, setOpen] = useState(false)

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-800/40 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <Info className="w-4 h-4 text-blue-400" />
          缠论概念速览
          <span className="text-xs font-normal text-slate-500">看不懂术语？点这里</span>
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-4">
          {CHAN_TERMS.map((t) => (
            <div key={t.key} className="bg-slate-800/40 rounded-lg p-3">
              <div className="text-sm font-semibold text-blue-300 mb-1">{t.name}</div>
              <p className="text-xs text-slate-400 leading-relaxed">{t.detail}</p>
            </div>
          ))}
          <div className="bg-slate-800/40 rounded-lg p-3 sm:col-span-2 lg:col-span-1">
            <div className="text-sm font-semibold text-amber-300 mb-1">三类买卖点</div>
            <p className="text-xs text-slate-400 leading-relaxed">
              一买/一卖最早出现（背驰反转），二买/二卖确认度更高（回踩不破 / 反弹不过），
              三买/三卖顺势确认（突破中枢并站稳）。从一到三，风险递减、确认度递增。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
