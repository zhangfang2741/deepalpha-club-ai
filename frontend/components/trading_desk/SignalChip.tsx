import type { Polarity } from '@/lib/api/trading_desk'

const STYLE: Record<Polarity, { box: string; dot: string; label: string }> = {
  bull: { box: 'bg-green-50 text-green-700', dot: 'bg-green-600', label: '看多' },
  bear: { box: 'bg-red-50 text-red-600', dot: 'bg-red-500', label: '看空' },
  neutral: { box: 'bg-amber-50 text-amber-700', dot: 'bg-amber-600', label: '中性' },
}

export default function SignalChip({
  dir,
  conf,
  extracted = false,
}: {
  dir: Polarity
  conf: number
  extracted?: boolean
}) {
  const s = STYLE[dir]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${s.box}`}
      // extracted 表示信号是我们从报告里抽取的，而非引擎原生产出——
      // 不标出来的话，用户会以为这是 agent 自己给的置信度
      title={extracted ? '由报告文本抽取得出，非 agent 原生输出' : undefined}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label} · {conf}
      {extracted && <span className="text-[10px] opacity-60">抽</span>}
    </span>
  )
}
