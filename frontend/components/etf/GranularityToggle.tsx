'use client'

import type { Granularity } from '@/lib/api/etf'

interface GranularityToggleProps {
  value: Granularity
  onChange: (g: Granularity) => void
  disabled?: boolean
}

const OPTIONS: { value: Granularity; label: string }[] = [
  { value: 'day', label: '日' },
  { value: 'week', label: '周' },
  { value: 'month', label: '月' },
]

export default function GranularityToggle({ value, onChange, disabled }: GranularityToggleProps) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors disabled:opacity-50 ${
            value === opt.value
              ? 'bg-white shadow-sm text-gray-900'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
