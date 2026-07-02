// 威科夫方法论术语解释（通俗中文）——界面提示与科普卡片的单一数据源

export interface GlossaryTerm {
  key: string
  name: string
  /** 一句话解释，用于点击小提示 */
  brief: string
  /** 详细解释，用于科普卡片 */
  detail: string
}

// 核心概念
export const WYCKOFF_TERMS: GlossaryTerm[] = [
  {
    key: 'trading_range',
    name: '交易区间',
    brief: '主力吸筹/派发时价格横盘震荡的区间，由支撑与阻力界定。',
    detail:
      '价格在一段横盘区间内反复震荡，主力（威科夫称之为“Composite Man 综合人”）在此悄悄吸筹或派发。区间下沿为支撑、上沿为阻力，突破区间往往意味着新趋势启动。',
  },
  {
    key: 'accumulation',
    name: '吸筹',
    brief: '下跌后主力在低位悄悄买入的横盘阶段，为后续拉升蓄势。',
    detail:
      '在明显下跌之后，价格进入横盘区间，主力借恐慌盘低位吸纳筹码。表现为下跌动能衰竭、缩量回踩不创新低，最终以向上突破结束。',
  },
  {
    key: 'distribution',
    name: '派发',
    brief: '上涨后主力在高位悄悄卖出的横盘阶段，为后续下跌蓄势。',
    detail:
      '在明显上涨之后，价格进入横盘区间，主力借追涨盘高位派发筹码。表现为上涨动能衰竭、反弹不创新高，最终以向下跌破结束。',
  },
  {
    key: 'markup',
    name: '拉升',
    brief: '吸筹完成后价格向上突破区间、趋势上行的阶段。',
    detail:
      '吸筹结束后，需求全面主导，价格向上突破交易区间进入趋势性上涨。回踩不破前期阻力（转为支撑）是健康拉升的标志。',
  },
  {
    key: 'markdown',
    name: '下跌',
    brief: '派发完成后价格向下跌破区间、趋势下行的阶段。',
    detail:
      '派发结束后，供给全面主导，价格向下跌破交易区间进入趋势性下跌。反弹不破前期支撑（转为阻力）是下跌延续的标志。',
  },
  {
    key: 'law_supply_demand',
    name: '定律一·供求关系',
    brief: '需求大于供给则涨，供给大于需求则跌。',
    detail:
      '威科夫第一定律。通过比较放量上涨与放量下跌的成交量，判断当前是买盘（需求）还是卖盘（供给）主导，从而推断价格方向。',
  },
  {
    key: 'law_cause_effect',
    name: '定律二·因果关系',
    brief: '横盘区间的“原因”越大，突破后的“结果”（涨跌幅）越大。',
    detail:
      '威科夫第二定律。交易区间内的横盘蓄势是“原因”，突破后的趋势幅度是“结果”。区间越宽、时间越久，突破后的量度目标越远。',
  },
  {
    key: 'law_effort_result',
    name: '定律三·量价关系',
    brief: '成交量是“努力”，价格波动是“结果”，两者背离预示反转。',
    detail:
      '威科夫第三定律（Effort vs Result）。若放大量（努力大）却价格滞涨/滞跌（结果小），说明有反向力量在吸收，往往预示趋势反转。',
  },
]

export const WYCKOFF_TERM_MAP: Record<string, GlossaryTerm> = Object.fromEntries(
  WYCKOFF_TERMS.map((t) => [t.key, t]),
)

// 威科夫事件释义
export interface EventGloss {
  name: string
  brief: string
}

export const EVENT_GLOSSARY: Record<string, EventGloss> = {
  PS: { name: '初步支撑 PS', brief: '下跌中首次放量承接，卖压开始被吸收。' },
  SC: { name: '卖出高潮 SC', brief: '恐慌抛售、极端放量宽幅下跌，常形成区间低点。' },
  AR: { name: '自动反弹/回落 AR', brief: '高潮后的反向摆动，界定交易区间的另一侧边界。' },
  ST: { name: '二次测试 ST', brief: '缩量回踩前期极值，测试供给/需求是否减轻。' },
  SPRING: { name: '弹簧 Spring', brief: '短暂跌破支撑后迅速收回的诱空，理想吸筹买点。' },
  TEST: { name: '测试 Test', brief: '对弹簧低点的低量回踩，确认下方无供给。' },
  SOS: { name: '强势信号 SOS', brief: '放量宽幅上涨逼近/突破区间上沿，需求主导。' },
  LPS: { name: '最后支撑点 LPS', brief: 'SOS 后回踩不创新低，是拉升前的介入点。' },
  BU: { name: '回踩确认 BU', brief: '突破区间后回抽上沿获得支撑（Back Up）。' },
  PSY: { name: '初步供给 PSY', brief: '上涨中首次放量遇阻，买压开始被消化。' },
  BC: { name: '买入高潮 BC', brief: '追涨放量宽幅上冲，常形成区间高点。' },
  UT: { name: '冲高回落 UT', brief: '短暂突破阻力后迅速回落的诱多。' },
  UTAD: { name: '派发后冲高 UTAD', brief: '派发末端的诱多突破，理想做空/离场点。' },
  SOW: { name: '弱势信号 SOW', brief: '放量宽幅下跌跌破区间下沿，供给主导。' },
  LPSY: { name: '最后供给点 LPSY', brief: 'SOW 后反弹无力、不创新高，是下跌前的离场点。' },
}

// 阶段颜色（bias → tailwind）
export const BIAS_STYLE: Record<string, { text: string; bg: string; border: string }> = {
  bullish: { text: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-800' },
  bearish: { text: 'text-red-400', bg: 'bg-red-950/40', border: 'border-red-800' },
  neutral: { text: 'text-slate-300', bg: 'bg-slate-800/60', border: 'border-slate-700' },
}
