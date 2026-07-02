'use client'
import { useState } from 'react'
import { ChevronDown, Info } from 'lucide-react'

const TERMS = [
  {
    name: '转换线 Tenkan（9）',
    detail: '近 9 期 (最高价+最低价)/2，反映短期均衡价，是最敏感的一条线。',
  },
  {
    name: '基准线 Kijun（26）',
    detail: '近 26 期中值，反映中期均衡价，常作为趋势与止损参考。',
  },
  {
    name: '先行带 A Senkou A',
    detail: '(转换线+基准线)/2，向前平移 26 期，构成云的一条边。',
  },
  {
    name: '先行带 B Senkou B',
    detail: '近 52 期中值，向前平移 26 期，构成云的另一条边。',
  },
  {
    name: '云 Kumo',
    detail: '先行带 A、B 之间的区域。A 在 B 上为阳云（支撑，看涨），A 在 B 下为阴云（压制，看跌）。',
  },
  {
    name: '迟行线 Chikou',
    detail: '当期收盘价向后平移 26 期。在价格之上偏多，之下偏空，用于确认。',
  },
]

// 顶部可折叠的「一目均衡表概念速览」科普
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
          一目均衡表概念速览
          <span className="text-xs font-normal text-slate-500">看不懂术语？点这里</span>
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-4">
          {TERMS.map((t) => (
            <div key={t.name} className="bg-slate-800/40 rounded-lg p-3">
              <div className="text-sm font-semibold text-blue-300 mb-1">{t.name}</div>
              <p className="text-xs text-slate-400 leading-relaxed">{t.detail}</p>
            </div>
          ))}
          <div className="bg-slate-800/40 rounded-lg p-3 sm:col-span-2 lg:col-span-1">
            <div className="text-sm font-semibold text-amber-300 mb-1">三役好转 / 逆转</div>
            <p className="text-xs text-slate-400 leading-relaxed">
              「三役」指价格相对云、转换线相对基准线、迟行线相对价格。三者同为多方即「三役好转」（强多），
              同为空方即「三役逆转」（强空），是一目均衡表最强的顺势确认。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
