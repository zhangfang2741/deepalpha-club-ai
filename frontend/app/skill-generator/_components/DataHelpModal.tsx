'use client'
import { useState } from 'react'

interface DataNode {
  title: string
  emoji: string
  description: string
  usage: string  // 在对话中怎么用
  example?: string
  children?: DataNode[]
}

const DATA_TREE: DataNode[] = [
  {
    title: '股票价格',
    emoji: '📈',
    description: 'K线历史走势（日线/周线）',
    usage: '描述"均线金叉"、"RSI 超卖"、"MACD 背离"等价格类因子时自动使用',
    example: '"20日均线上穿50日均线买入信号"',
    children: [
      { title: '每日价格变化', emoji: '📊', description: '开盘、收盘、最高、最低价', usage: '"收盘价高于开盘价时买入"' },
      { title: '成交量', emoji: '🔥', description: '每日成交股数', usage: '"成交量放大超过3倍"' },
    ],
  },
  {
    title: '公司财务',
    emoji: '💼',
    description: '每季度发布的财报数据',
    usage: '描述"盈利预期上调"、"净利润增长"、"毛利率提升"等基本面因子时使用',
    example: '"单季净利润同比上涨超过20%"',
    children: [
      {
        title: '盈利能力',
        emoji: '💰',
        description: '收入、净利润、毛利、每股收益',
        usage: '"营收同比增长"、"净利率提升"',
      },
      {
        title: '资产与负债',
        emoji: '🏦',
        description: '总资产、总负债、现金、债务',
        usage: '"资产负债率低于50%"、"现金充足"',
      },
      {
        title: '现金流',
        emoji: '💵',
        description: '经营现金流、自由现金流、资本支出',
        usage: '"经营现金流为正"、"自由现金流充裕"',
      },
    ],
  },
  {
    title: '估值指标',
    emoji: '🎯',
    description: 'PE、PB、PS 等估值比率',
    usage: '描述"低估值买入"、"PE 在历史低位"等估值择时因子',
    example: '"PE低于历史30%分位"',
    children: [
      { title: '市盈率', emoji: '📊', description: 'PE = 股价/每股收益', usage: '"PE低于行业平均"' },
      { title: '市净率', emoji: '📋', description: 'PB = 股价/每股净资产', usage: '"PB低于1.5倍"' },
      { title: '股息率', emoji: '💸', description: '年度股息/股价', usage: '"股息率超过3%"' },
    ],
  },
  {
    title: '分析师预测',
    emoji: '👥',
    description: '华尔街分析师的一致预期',
    usage: '描述"盈利预期上调"、"营收超预期"等事件驱动因子',
    example: '"EPS共识预测较上季度上调超过10%"',
    children: [
      { title: 'EPS预测', emoji: '📈', description: '共识、最高、最低 EPS 预测', usage: '"多家机构上调EPS"' },
      { title: '营收预测', emoji: '📊', description: '共识营收及高/低价', usage: '"营收有望超预期"' },
      { title: 'EPS惊喜', emoji: '🎁', description: '实际EPS vs 预期EPS之差', usage: '"财报EPS大幅超预期"' },
    ],
  },
  {
    title: '新闻与舆情',
    emoji: '📰',
    description: '股票相关新闻及情绪分析',
    usage: '描述"新闻情绪偏多"、"媒体负面报道"等舆情因子',
    example: '"最近30天平均新闻情绪偏正面"',
    children: [
      { title: '情绪分数', emoji: '😊', description: '-1到1，正值乐观', usage: '"情绪分数由负转正"' },
      { title: '情绪标签', emoji: '🏷️', description: 'positive/negative/neutral', usage: '"负面新闻数量减少"' },
      { title: '新闻原文', emoji: '📝', description: '可做 NLP 关键词提取', usage: '"提及管理层回购"' },
    ],
  },
  {
    title: '股息与回购',
    emoji: '💎',
    description: '股息历史与股票拆分',
    usage: '描述"高股息率"、"除权除息效应"等因子',
    example: '"股息率排名全市场前10%"',
    children: [
      { title: '股息历史', emoji: '💰', description: '每股股息金额与股息率', usage: '"连续5年分红"' },
      { title: 'DCF内在价值', emoji: '📐', description: '现金流折算估值', usage: '"当前股价低于DCF内在价值20%""' },
    ],
  },
  {
    title: '大盘与宏观',
    emoji: '🌍',
    description: '美国国债收益率、S&P500 指数',
    usage: '描述"利率上升利空股市"、"大盘择时"等宏观因子',
    example: '"10年期国债收益率突破4%"',
    children: [
      { title: '国债收益率', emoji: '📉', description: '1月/2年/10年/30年期', usage: '"收益率曲线倒挂预警衰退""' },
      { title: 'S&P500指数', emoji: '🏛️', description: '大盘整体走势', usage: '"SP500站上200日均线""' },
    ],
  },
  {
    title: '员工与公司规模',
    emoji: '👥',
    description: '员工历史人数（年度时间序列）',
    usage: '描述"员工增长超过20%"、"公司规模扩张"等因子时使用',
    example: '"员工同比增长超过20%"',
    children: [
      { title: '员工历史', emoji: '📊', description: '年度员工数量时间序列', usage: '"员工连续2年增长"' },
      { title: '公司概况', emoji: '🏢', description: '行业/市值/员工数', usage: '"市值超过1000亿美元"' },
    ],
  },
]

const QUICK_PHRASES = [
  '基于盈利预期上调',
  '低估值+高股息',
  '新闻情绪由负转正',
  '净利润连续增长',
  '量价齐升突破阻力位',
  '宏观利率下行受益',
]

export function DataHelpModal() {
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (path: string) => {
    const next = new Set(expanded)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setExpanded(next)
  }

  const copyPhrase = (phrase: string) => {
    navigator.clipboard.writeText(phrase)
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-colors"
        title="数据说明"
      >
        ？数据介绍
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto m-4">
            {/* Header */}
            <div className="sticky top-0 bg-white border-b border-gray-100 px-5 py-4 flex items-center justify-between z-10">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">数据介绍</h2>
                <p className="text-xs text-gray-400 mt-0.5">告诉 AI 你想要什么，它会自动选用这些数据</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                ×
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* 数据树 */}
              {DATA_TREE.map((node, i) => (
                <NodeRow key={i} node={node} path={String(i)} expanded={expanded} onToggle={toggle} depth={0} />
              ))}

              {/* 快捷短语 */}
              <div className="border-t border-gray-100 pt-4">
                <p className="text-sm font-medium text-gray-700 mb-3">💬 常用对话示例（点击复制）</p>
                <div className="flex flex-wrap gap-2">
                  {QUICK_PHRASES.map((phrase) => (
                    <button
                      key={phrase}
                      onClick={() => copyPhrase(phrase)}
                      className="text-xs px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 hover:border-blue-300 transition-colors"
                      title="点击复制"
                    >
                      {phrase}
                    </button>
                  ))}
                </div>
              </div>

              {/* 底部说明 */}
              <div className="bg-gray-50 rounded-lg p-4 text-xs text-gray-500">
                <p>💡 <span className="font-medium text-gray-700">提示：</span>只需在左侧对话框用自然语言描述你的策略，AI 会自动选用所需数据并生成因子代码。例如：</p>
                <p className="mt-1.5 text-gray-600">"PE低于20且近3个月新闻情绪平均为正值的股票"</p>
                <p className="mt-1.5 text-gray-600">"营收增长加速且分析师EPS预测上调的中小盘股"</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function NodeRow({ node, path, expanded, onToggle, depth }: {
  node: DataNode
  path: string
  expanded: Set<string>
  onToggle: (path: string) => void
  depth: number
}) {
  const hasChildren = node.children && node.children.length > 0
  const isExpanded = expanded.has(path)
  const paddingLeft = 12 + depth * 20

  return (
    <div>
      <div
        className="flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer"
        style={{ paddingLeft }}
        onClick={() => hasChildren && onToggle(path)}
      >
        {hasChildren ? (
          <span className="text-gray-400 text-xs mt-0.5 w-4">{isExpanded ? '▼' : '▶'}</span>
        ) : (
          <span className="w-4" />
        )}
        <span className="text-xl">{node.emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-800">{node.title}</span>
            {node.example && (
              <span className="text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded truncate max-w-[180px]">
                {node.example}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{node.description}</p>
          {depth === 0 && node.usage && (
            <p className="text-xs text-gray-400 mt-1 line-clamp-1">用法：{node.usage}</p>
          )}
        </div>
      </div>

      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child, ci) => (
            <NodeRow
              key={ci}
              node={child}
              path={`${path}-${ci}`}
              expanded={expanded}
              onToggle={onToggle}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}