'use client'
import { useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'
import { WYCKOFF_TERMS, EVENT_GLOSSARY } from '@/lib/wyckoff-glossary'

// 顶部可折叠的「威科夫概念速览」：给不熟悉威科夫方法的用户做科普
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
          威科夫方法论速览
          <span className="text-xs font-normal text-slate-500">看不懂术语？点这里</span>
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {WYCKOFF_TERMS.map((t) => (
              <div key={t.key} className="bg-slate-800/40 rounded-lg p-3">
                <div className="text-sm font-semibold text-blue-300 mb-1">{t.name}</div>
                <p className="text-xs text-slate-400 leading-relaxed">{t.detail}</p>
              </div>
            ))}
          </div>

          <div>
            <div className="text-sm font-semibold text-amber-300 mb-2">威科夫事件速查</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {Object.entries(EVENT_GLOSSARY).map(([code, g]) => (
                <div key={code} className="bg-slate-800/40 rounded-lg px-3 py-2">
                  <span className="text-xs font-semibold text-slate-200">{g.name}</span>
                  <p className="text-xs text-slate-400 leading-relaxed mt-0.5">{g.brief}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
