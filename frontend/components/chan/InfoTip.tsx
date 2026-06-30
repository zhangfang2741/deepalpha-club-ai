'use client'
import { Popover } from '@base-ui/react/popover'
import { CircleHelp } from 'lucide-react'

interface InfoTipProps {
  title?: string
  content: string
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

// 行内问号提示：改用 Popover（点击触发），桌面与移动端都能点开；
// portal 渲染避免被父容器 overflow 裁切
export function InfoTip({ title, content, side = 'top', className }: InfoTipProps) {
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={title ?? '说明'}
        className={`inline-flex items-center justify-center align-middle text-slate-500 hover:text-blue-400 transition-colors cursor-pointer ${className ?? ''}`}
      >
        <CircleHelp className="w-3.5 h-3.5" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side={side} sideOffset={6} className="z-50">
          <Popover.Popup className="max-w-[260px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs leading-relaxed shadow-xl">
            {title && <div className="font-semibold text-slate-100 mb-0.5">{title}</div>}
            <p className="text-slate-300">{content}</p>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
