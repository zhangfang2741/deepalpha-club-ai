'use client'

import { useState } from 'react'
import { makeAssistantToolUI, type ToolCallMessagePartProps } from '@assistant-ui/react'
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Circle,
  CircleDot,
  Wrench,
  ListChecks,
  Bot,
  Search,
} from 'lucide-react'

// 工具名 → 中文友好标签与图标
const TOOL_LABELS: Record<string, { label: string; Icon: typeof Wrench }> = {
  duckduckgo_search: { label: '联网搜索', Icon: Search },
  chan_analysis: { label: '缠论分析', Icon: Wrench },
  wyckoff_analysis: { label: '威科夫分析', Icon: Wrench },
  ichimoku_analysis: { label: '一目均衡表分析', Icon: Wrench },
  structure_gap_analysis: { label: '结构背离分析', Icon: Wrench },
  ask_human: { label: '向你确认', Icon: Bot },
  write_todos: { label: '任务规划', Icon: ListChecks },
  task: { label: '子任务', Icon: Bot },
  ls: { label: '列出文件', Icon: Wrench },
  read_file: { label: '读取文件', Icon: Wrench },
  write_file: { label: '写入文件', Icon: Wrench },
  edit_file: { label: '编辑文件', Icon: Wrench },
}

function toolMeta(toolName: string) {
  return TOOL_LABELS[toolName] ?? { label: toolName, Icon: Wrench }
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

/** 通用工具调用卡片：折叠展示参数与结果。 */
export function ToolFallback({
  toolName,
  args,
  result,
  status,
  isError,
}: ToolCallMessagePartProps) {
  const [open, setOpen] = useState(false)
  const { label, Icon } = toolMeta(toolName)
  const running = isRunning(status)

  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-gray-50 text-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-gray-100 transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
        )}
        <Icon className="h-4 w-4 text-indigo-500 flex-shrink-0" />
        <span className="font-medium text-gray-700">{label}</span>
        {running ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500 ml-1" />
        ) : (
          <CheckCircle2
            className={`h-3.5 w-3.5 ml-1 ${isError ? 'text-red-500' : 'text-emerald-500'}`}
          />
        )}
        <span className="ml-auto text-xs text-gray-400">{running ? '执行中…' : '已完成'}</span>
      </button>

      {open && (
        <div className="border-t border-gray-200 px-3 py-2 space-y-2">
          {args != null && Object.keys(args as object).length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-500 mb-1">参数</div>
              <pre className="text-xs bg-white rounded border border-gray-200 p-2 overflow-x-auto whitespace-pre-wrap break-words">
                {formatValue(args)}
              </pre>
            </div>
          )}
          {result != null && (
            <div>
              <div className="text-xs font-semibold text-gray-500 mb-1">结果</div>
              <pre className="text-xs bg-white rounded border border-gray-200 p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                {formatValue(result)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface TodoItem {
  content?: string
  status?: 'pending' | 'in_progress' | 'completed' | string
}

/** write_todos（Deep Agent 规划）：渲染成待办清单。 */
export const WriteTodosToolUI = makeAssistantToolUI<{ todos?: TodoItem[] }, unknown>({
  toolName: 'write_todos',
  render: ({ args }) => {
    const todos = args?.todos ?? []
    if (todos.length === 0) {
      return (
        <div className="my-2 flex items-center gap-2 text-sm text-gray-500">
          <ListChecks className="h-4 w-4 text-indigo-500" />
          正在规划任务…
        </div>
      )
    }
    return (
      <div className="my-2 rounded-lg border border-indigo-100 bg-indigo-50/60 px-3 py-2.5 text-sm">
        <div className="flex items-center gap-2 mb-2 font-medium text-indigo-700">
          <ListChecks className="h-4 w-4" />
          任务规划
        </div>
        <ul className="space-y-1.5">
          {todos.map((todo, i) => {
            const s = todo.status
            return (
              <li key={i} className="flex items-start gap-2">
                {s === 'completed' ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                ) : s === 'in_progress' ? (
                  <CircleDot className="h-4 w-4 text-indigo-500 flex-shrink-0 mt-0.5 animate-pulse" />
                ) : (
                  <Circle className="h-4 w-4 text-gray-300 flex-shrink-0 mt-0.5" />
                )}
                <span
                  className={
                    s === 'completed'
                      ? 'text-gray-400 line-through'
                      : s === 'in_progress'
                        ? 'text-gray-800 font-medium'
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
      <div className="my-2 rounded-lg border border-violet-100 bg-violet-50/60 px-3 py-2.5 text-sm">
        <div className="flex items-center gap-2 font-medium text-violet-700">
          <Bot className="h-4 w-4" />
          子任务
          {args?.subagent_type && (
            <span className="text-xs font-normal text-violet-400">({args.subagent_type})</span>
          )}
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500 ml-1" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 ml-1" />
          )}
        </div>
        {args?.description && (
          <p className="mt-1 text-gray-600 whitespace-pre-wrap break-words">{args.description}</p>
        )}
        {result != null && !running && (
          <pre className="mt-2 text-xs bg-white rounded border border-violet-100 p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
            {formatValue(result)}
          </pre>
        )}
      </div>
    )
  },
})
