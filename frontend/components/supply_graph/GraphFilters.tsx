'use client'

export default function GraphFilters({ depth, direction, onDepth, onDirection }: { depth: number; direction: string; onDepth: (value: number) => void; onDirection: (value: string) => void }) {
  return <div className="flex gap-3 text-sm"><select value={depth} onChange={(event) => onDepth(Number(event.target.value))} className="rounded-lg border px-3 py-2">{[1, 2, 3].map((value) => <option key={value} value={value}>{value} 度</option>)}</select><select value={direction} onChange={(event) => onDirection(event.target.value)} className="rounded-lg border px-3 py-2"><option value="upstream">上游</option><option value="downstream">下游</option><option value="both">双向</option></select></div>
}
