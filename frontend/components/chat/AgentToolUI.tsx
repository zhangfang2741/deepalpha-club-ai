'use client'

import { useState } from 'react'
import { makeAssistantToolUI, type ToolCallMessagePartProps } from '@assistant-ui/react'
import {
  ChevronDown,
  Loader2,
  CheckCircle2,
  Circle,
  CircleDot,
  Wrench,
  ListChecks,
  Bot,
  Search,
  LineChart,
  FileText,
  MessageCircleQuestion,
  AlertTriangle,
  type LucideIcon,
} from 'lucide-react'

type ToolCategory = 'search' | 'analysis' | 'file' | 'human' | 'plan' | 'subagent' | 'generic'

interface ToolMeta {
  label: string
  Icon: LucideIcon
  category: ToolCategory
}

// 工具名 → 中文标签 / 图标 / 视觉分类
const TOOL_LABELS: Record<string, ToolMeta> = {
  duckduckgo_search: { label: '联网搜索', Icon: Search, category: 'search' },
  chan_analysis: { label: '缠论分析', Icon: LineChart, category: 'analysis' },
  wyckoff_analysis: { label: '威科夫分析', Icon: LineChart, category: 'analysis' },
  ichimoku_analysis: { label: '一目均衡表分析', Icon: LineChart, category: 'analysis' },
  structure_gap_analysis: { label: '结构背离分析', Icon: LineChart, category: 'analysis' },
  ask_human: { label: '向你确认', Icon: MessageCircleQuestion, category: 'human' },
  write_todos: { label: '任务规划', Icon: ListChecks, category: 'plan' },
  task: { label: '子任务', Icon: Bot, category: 'subagent' },
  ls: { label: '列出文件', Icon: FileText, category: 'file' },
  read_file: { label: '读取文件', Icon: FileText, category: 'file' },
  write_file: { label: '写入文件', Icon: FileText, category: 'file' },
  edit_file: { label: '编辑文件', Icon: FileText, category: 'file' },
}

// 分类 → 强调色（图标底色 / 左侧描边），保持与 app 现有 gray/indigo 体系协调
const CATEGORY_ACCENT: Record<ToolCategory, { chip: string; ring: string }> = {
  search: { chip: 'bg-sky-50 text-sky-600', ring: 'border-l-sky-300' },
  analysis: { chip: 'bg-indigo-50 text-indigo-600', ring: 'border-l-indigo-300' },
  file: { chip: 'bg-slate-100 text-slate-500', ring: 'border-l-slate-300' },
  human: { chip: 'bg-amber-50 text-amber-600', ring: 'border-l-amber-300' },
  plan: { chip: 'bg-indigo-50 text-indigo-600', ring: 'border-l-indigo-300' },
  subagent: { chip: 'bg-violet-50 text-violet-600', ring: 'border-l-violet-300' },
  generic: { chip: 'bg-gray-100 text-gray-500', ring: 'border-l-gray-300' },
}

function toolMeta(toolName: string): ToolMeta {
  return TOOL_LABELS[toolName] ?? { label: toolName, Icon: Wrench, category: 'generic' }
}

function isRunning(status: ToolCallMessagePartProps['status']): boolean {
  return status?.type === 'running' || status?.type === 'requires-action'
}

function formatValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/** 判断是否为「扁平简单对象」（值均为原始类型），用于决定参数以 KV 还是 JSON 呈现。 */
function isFlatSimple(obj: unknown): obj is Record<string, unknown> {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    !Array.isArray(obj) &&
    Object.values(obj).every((v) => v == null || typeof v !== 'object')
  )
}

/** 状态徽标：执行中（脉冲点）/ 已完成（✓）/ 失败（红）。 */
function StatusBadge({ running, isError }: { running: boolean; isError?: boolean }) {
  if (running) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-indigo-500" />
        </span>
        执行中
      </span>
    )
  }
  if (isError) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600">
        <AlertTriangle className="h-3 w-3" />
        失败
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-600">
      <CheckCircle2 className="h-3 w-3" />
      已完成
    </span>
  )
}

/** 参数区：扁平对象渲染成 KV 列表，复杂结构回退到 JSON。 */
function ArgsView({ args }: { args: unknown }) {
  if (args == null) return null
  if (isFlatSimple(args)) {
    const entries = Object.entries(args).filter(([, v]) => v != null && v !== '')
    if (entries.length === 0) return null
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-medium text-gray-400">{k}</dt>
            <dd className="text-gray-700 break-words">{String(v)}</dd>
          </div>
        ))}
      </dl>
    )
  }
  const text = formatValue(args)
  if (!text) return null
  return (
    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-gray-50 p-2 text-xs text-gray-600">
      {text}
    </pre>
  )
}

/** 结果区：长文本报告用可读排版呈现，其余回退 JSON。 */
function ResultView({ result }: { result: unknown }) {
  if (result == null) return null
  const text = formatValue(result)
  if (!text.trim()) return null
  const isReport = typeof result === 'string' && text.length > 80
  return (
    <div
      className={
        isReport
          ? 'max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-white p-2.5 text-xs leading-relaxed text-gray-700 ring-1 ring-gray-100'
          : 'max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-gray-50 p-2 font-mono text-xs text-gray-600'
      }
    >
      {text}
    </div>
  )
}

/** 通用工具调用卡片：折叠展示参数与结果，带分类强调色与状态徽标。 */
export function ToolFallback({ toolName, args, result, status, isError }: ToolCallMessagePartProps) {
  const [open, setOpen] = useState(false)
  const { label, Icon, category } = toolMeta(toolName)
  const accent = CATEGORY_ACCENT[category]
  const running = isRunning(status)
  const hasBody =
    (args != null && (!isFlatSimple(args) || Object.keys(args).length > 0)) || result != null

  return (
    <div
      className={`my-2 overflow-hidden rounded-xl border border-gray-200 border-l-[3px] ${accent.ring} bg-white shadow-sm`}
    >
      <button
        type="button"
        onClick={() => hasBody && setOpen((v) => !v)}
        className={`flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors ${
          hasBody ? 'hover:bg-gray-50' : 'cursor-default'
        }`}
      >
        <span className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg ${accent.chip}`}>
          <Icon className="h-4 w-4" />
        </span>
        <span className="text-sm font-medium text-gray-800">{label}</span>
        <span className="ml-auto flex items-center gap-2">
          <StatusBadge running={running} isError={isError} />
          {hasBody && (
            <ChevronDown
              className={`h-4 w-4 text-gray-300 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
            />
          )}
        </span>
      </button>

      {/* grid 0fr→1fr 实现平滑高度展开 */}
      <div className={`grid transition-all duration-200 ease-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden">
          <div className="space-y-2.5 border-t border-gray-100 px-3 py-2.5">
            {args != null && (
              <div className="space-y-1">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">参数</div>
                <ArgsView args={args} />
              </div>
            )}
            {result != null && (
              <div className="space-y-1">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">结果</div>
                <ResultView result={result} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

interface TodoItem {
  content?: string
  status?: 'pending' | 'in_progress' | 'completed' | string
}

/** write_todos（Deep Agent 规划）：渲染成带进度条与连线的任务时间线。 */
export const WriteTodosToolUI = makeAssistantToolUI<{ todos?: TodoItem[] }, unknown>({
  toolName: 'write_todos',
  render: ({ args }) => {
    const todos = args?.todos ?? []
    if (todos.length === 0) {
      return (
        <div className="my-2 flex items-center gap-2 rounded-xl border border-indigo-100 bg-indigo-50/50 px-3 py-2.5 text-sm text-indigo-600">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在规划任务…
        </div>
      )
    }
    const done = todos.filter((t) => t.status === 'completed').length
    const pct = Math.round((done / todos.length) * 100)

    return (
      <div className="my-2 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/70 to-white px-3.5 py-3 text-sm shadow-sm">
        <div className="mb-2.5 flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-indigo-500" />
          <span className="font-semibold text-indigo-700">任务规划</span>
          <span className="ml-auto text-xs font-medium text-indigo-400">
            {done}/{todos.length} 完成
          </span>
        </div>
        <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
          <div
            className="h-full rounded-full bg-indigo-500 transition-all duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <ul className="space-y-0">
          {todos.map((todo, i) => {
            const s = todo.status
            const isLast = i === todos.length - 1
            return (
              <li key={i} className="relative flex gap-2.5 pb-2.5 last:pb-0">
                {/* 连线 */}
                {!isLast && <span className="absolute left-[7px] top-5 h-full w-px bg-indigo-100" />}
                <span className="relative z-10 mt-0.5 flex-shrink-0">
                  {s === 'completed' ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  ) : s === 'in_progress' ? (
                    <CircleDot className="h-3.5 w-3.5 animate-pulse text-indigo-500" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 text-gray-300" />
                  )}
                </span>
                <span
                  className={
                    s === 'completed'
                      ? 'text-gray-400 line-through'
                      : s === 'in_progress'
                        ? 'font-medium text-gray-800'
                        : 'text-gray-600'
                  }
                >
                  {todo.content}
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    )
  },
})

/** task（子智能体委派）：展示子任务描述与结果。 */
export const TaskToolUI = makeAssistantToolUI<
  { description?: string; subagent_type?: string },
  unknown
>({
  toolName: 'task',
  render: ({ args, result, status }) => {
    const running = isRunning(status)
    return (
      <div className="my-2 rounded-xl border border-violet-100 border-l-[3px] border-l-violet-300 bg-white px-3.5 py-3 text-sm shadow-sm">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
            <Bot className="h-4 w-4" />
          </span>
          <span className="font-medium text-gray-800">子任务</span>
          {args?.subagent_type && (
            <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] text-violet-500">
              {args.subagent_type}
            </span>
          )}
          <span className="ml-auto">
            <StatusBadge running={running} />
          </span>
        </div>
        {args?.description && (
          <p className="mt-2 whitespace-pre-wrap break-words text-gray-600">{args.description}</p>
        )}
        {result != null && !running && (
          <div className="mt-2">
            <ResultView result={result} />
          </div>
        )}
      </div>
    )
  },
})
