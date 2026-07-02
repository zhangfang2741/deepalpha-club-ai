'use client'
import type { WyckoffAnalysisResult } from '@/lib/api/wyckoff'
import { InfoTip } from './InfoTip'
import { BIAS_STYLE, EVENT_GLOSSARY } from '@/lib/wyckoff-glossary'

interface Props {
  data: WyckoffAnalysisResult
}

// 偏空事件用红色系，偏多/中性事件用绿色系
const BEARISH_EVENTS = new Set(['BC', 'UT', 'UTAD', 'SOW', 'LPSY', 'PSY'])

const STAGE_BADGE: Record<string, string> = {
  accumulation: 'bg-emerald-950/50 text-emerald-300 border-emerald-800',
  markup: 'bg-green-950/50 text-green-300 border-green-800',
  distribution: 'bg-red-950/50 text-red-300 border-red-800',
  markdown: 'bg-rose-950/50 text-rose-300 border-rose-800',
  undetermined: 'bg-slate-800/60 text-slate-300 border-slate-700',
}

export function EventPanel({ data }: Props) {
  const rec = data.recommendation
  const biasStyle = rec ? BIAS_STYLE[rec.bias] ?? BIAS_STYLE.neutral : BIAS_STYLE.neutral

  return (
    <div className="flex flex-col gap-4 text-sm">
      {/* 阶段总览 */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">市场阶段</span>
        </div>
        <div
          className={`inline-flex items-center rounded-lg border px-3 py-1.5 text-sm font-semibold ${
            STAGE_BADGE[data.phase?.stage ?? 'undetermined'] ?? STAGE_BADGE.undetermined
          }`}
        >
          {data.stage_label || '结构不明'}
        </div>
        {data.phase?.phase_label && (
          <p className="text-xs text-slate-400 mt-2">{data.phase.phase_label}</p>
        )}
        {data.position_desc && (
          <p className="text-xs text-slate-500 mt-1">{data.position_desc}</p>
        )}
      </div>

      {/* 操作建议 */}
      {rec && (
        <div className={`rounded-lg border p-3 ${biasStyle.bg} ${biasStyle.border}`}>
          <div className={`font-semibold ${biasStyle.text}`}>{rec.action_label}</div>
          <ul className="mt-2 flex flex-col gap-1 text-xs text-slate-300 list-disc list-inside">
            {rec.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          {rec.caveats.length > 0 && (
            <p className="mt-2 text-[11px] text-slate-500 leading-relaxed">
              {rec.caveats.join('；')}
            </p>
          )}
        </div>
      )}

      {/* 交易区间 */}
      {data.trading_range && (
        <div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            交易区间（{data.trading_range.kind === 'accumulation' ? '吸筹' : '派发'}）
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-slate-800/40 rounded-lg px-3 py-2">
              <div className="text-[11px] text-slate-500">阻力</div>
              <div className="text-slate-200 font-medium">{data.trading_range.resistance.toFixed(2)}</div>
            </div>
            <div className="bg-slate-800/40 rounded-lg px-3 py-2">
              <div className="text-[11px] text-slate-500">支撑</div>
              <div className="text-slate-200 font-medium">{data.trading_range.support.toFixed(2)}</div>
            </div>
          </div>
        </div>
      )}

      {/* 三大定律 */}
      {data.laws.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            威科夫三大定律
          </div>
          <div className="flex flex-col gap-2">
            {data.laws.map((law) => (
              <div key={law.key} className="bg-slate-800/40 rounded-lg px-3 py-2">
                <div className="text-xs font-semibold text-slate-200">{law.name}</div>
                <div className="text-xs text-slate-300 mt-0.5">{law.verdict}</div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{law.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 事件序列 */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
          威科夫事件（{data.events.length}）
        </div>
        {data.events.length === 0 ? (
          <p className="text-xs text-slate-500">未识别到明确的威科夫事件</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {data.events.map((e, i) => {
              const bearish = BEARISH_EVENTS.has(e.code)
              const g = EVENT_GLOSSARY[e.code]
              return (
                <div
                  key={i}
                  className={`rounded-lg border px-3 py-2 ${
                    bearish
                      ? 'bg-red-950/30 border-red-900/60'
                      : 'bg-emerald-950/30 border-emerald-900/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-100">
                      {e.name}
                      <span className="text-[11px] font-mono text-slate-400">{e.code}</span>
                      {g && <InfoTip title={g.name} content={g.brief} side="left" />}
                    </span>
                    <span className="text-[11px] text-slate-500">{e.phase} 阶段</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1">
                    <span>{e.time}</span>
                    <span>
                      价 {e.price.toFixed(2)} · 量比 {e.volume_ratio.toFixed(1)}×
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 分析摘要 */}
      {data.summary && (
        <div className="text-xs text-slate-400 leading-relaxed border-t border-slate-800 pt-3">
          {data.summary}
        </div>
      )}
    </div>
  )
}
