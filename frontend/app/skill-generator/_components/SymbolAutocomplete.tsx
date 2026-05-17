'use client'
import { useEffect, useRef, useState } from 'react'
import { searchSymbol, type SymbolSuggestion } from '@/lib/api/skills'

interface Props {
  value: string
  onChange: (symbol: string) => void
  placeholder?: string
}

export function SymbolAutocomplete({ value, onChange, placeholder = '如 NVDA、AAPL、TSLA' }: Props) {
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // 输入变化时 debounce 300ms 触发搜索
  useEffect(() => {
    const q = value.trim()
    if (!q) {
      setSuggestions([])
      return
    }
    setLoading(true)
    const timer = setTimeout(async () => {
      try {
        const list = await searchSymbol(q, 10)
        setSuggestions(list)
        setActiveIndex(-1)
      } catch (e) {
        console.error('[SymbolAutocomplete] search failed:', e)
        setSuggestions([])
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [value])

  // 点击外部关闭下拉
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const handleSelect = (s: SymbolSuggestion) => {
    onChange(s.symbol)
    setOpen(false)
    setActiveIndex(-1)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (i - 1 + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault()
      handleSelect(suggestions[activeIndex])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showDropdown = open && value.trim().length > 0

  return (
    <div ref={containerRef} className="relative">
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase())
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        autoComplete="off"
      />
      {showDropdown && (
        <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-72 overflow-y-auto">
          {loading && suggestions.length === 0 && (
            <div className="px-3 py-2 text-sm text-gray-400">搜索中…</div>
          )}
          {!loading && suggestions.length === 0 && (
            <div className="px-3 py-2 text-sm text-gray-400">无匹配</div>
          )}
          {suggestions.map((s, i) => (
            <button
              key={`${s.symbol}-${s.exchange}`}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(s)}
              className={`w-full text-left px-3 py-2 flex items-baseline gap-2 hover:bg-blue-50 transition-colors ${
                i === activeIndex ? 'bg-blue-50' : ''
              }`}
            >
              <span className="font-mono font-semibold text-gray-900">{s.symbol}</span>
              <span className="text-sm text-gray-600 truncate flex-1">{s.name}</span>
              <span className="text-xs text-gray-400">{s.exchange}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
