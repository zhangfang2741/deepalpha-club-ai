'use client'
import { Tooltip } from '@base-ui/react/tooltip'
import { CircleHelp } from 'lucide-react'

interface InfoTipProps {
  title?: string
  content: string
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

// 行内问号提示：hover 显示术语解释，base-ui 通过 portal 渲染，不会被父容器 overflow 裁切
export function InfoTip({ title, content, side = 'top', className }: InfoTipProps) {
  return (
    <Tooltip.Provider delay={120}>
      <Tooltip.Root>
        <Tooltip.Trigger
          aria-label={title ?? '说明'}
          className={`inline-flex items-center justify-center align-middle text-slate-500 hover:text-blue-400 transition-colors cursor-help ${className ?? ''}`}
        >
          <CircleHelp className="w-3.5 h-3.5" />
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Positioner side={side} sideOffset={6} className="z-50">
            <Tooltip.Popup className="max-w-[260px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs leading-relaxed shadow-xl">
              {title && <div className="font-semibold text-slate-100 mb-0.5">{title}</div>}
              <p className="text-slate-300">{content}</p>
            </Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
