import SwiftUI

/// 详情页最上方的结论卡：第一眼回答「现在什么状态、最新信号是什么、次级别怎么说」。
///
/// 以前这些答案压在图表 + MACD + 图例 + 三个 Tab 之后，第一屏看不到结论。阶段标题的
/// 颜色与自选列表的状态标签同一套（Theme.phaseColor，中性蓝）；一句话解读由阶段 + 方向在端上生成，
/// 只描述结构本身，不给操作建议。
///
/// 卡片分三层，样式各不相同，避免「红绿」被读成买卖：
/// 1. 已成立的买卖点（「最新信号」格）：红 / 绿实心，是事实；
/// 2. 待确认候选（同一格下方小字）：灰色虚线，不算买卖点；
/// 3. 结构阶段（标题）：中性蓝 + 方向箭头，只描述价格与中枢的关系。
struct ConclusionCard: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    var isStatic = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            headline
            HStack(spacing: 8) {
                latestSignalTile
                SubLevelTile(vm: vm, isStatic: isStatic)
            }
            legend
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(tint.opacity(0.35), lineWidth: 1))
    }

    private var phase: PivotPhase? { analysis.pivotPhase }

    private var tint: Color {
        guard let phase else { return Theme.border }
        return Theme.phaseColor(phase: phase.phase, direction: phase.direction)
    }

    @ViewBuilder
    private var headline: some View {
        if let phase {
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    HStack(spacing: 5) {
                        if let arrow = Theme.phaseArrow(direction: phase.direction) {
                            Image(systemName: arrow)
                                .font(.system(size: 17, weight: .heavy))
                                .accessibilityLabel(phase.direction == "up" ? L("价格向上") : L("价格向下"))
                        }
                        Text(phase.phaseLabel)
                            .font(.system(size: 21, weight: .heavy))
                    }
                    .foregroundStyle(tint)
                    if let word = Self.structureWord(phase) {
                        Text(word)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(tint.opacity(0.85))
                    }
                    Spacer(minLength: 0)
                    if !phase.confirmed {
                        Label(L("未确认"), systemImage: "circle.dashed")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                Text(Self.plainSentence(phase))
                    .font(.footnote)
                    .foregroundStyle(Theme.textPrimary.opacity(0.85))
                    .fixedSize(horizontal: false, vertical: true)
            }
        } else {
            VStack(alignment: .leading, spacing: 5) {
                Text(L("结构尚未成形"))
                    .font(.system(size: 19, weight: .heavy))
                    .foregroundStyle(Theme.textPrimary)
                Text(L("数据还不足以判断所处阶段，可先看图上的笔和中枢"))
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - 最新信号

    private var latestSignal: Signal? { analysis.signals.max { $0.displayTime < $1.displayTime } }
    /// 比最新买卖点更新的「待确认」候选（仅严格口径产出）：结论卡上也提示，但标明待确认。
    private var newerCandidate: Signal? {
        guard let c = analysis.candidates.max(by: { $0.displayTime < $1.displayTime }) else { return nil }
        // 同一天的候选也要显示（APP 2026-09-01：一买与待确认三卖同在 08-31，以前被藏起来，
        // 用户只在图上看到虚线「卖 3」，对不上这里）；只有比最新买卖点更早的才不提
        if let s = latestSignal, s.displayTime > c.displayTime { return nil }
        return c
    }

    private var latestSignalTile: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(L("最新信号")).font(.caption2).foregroundStyle(Theme.textSecondary)
            if let s = latestSignal {
                HStack(spacing: 4) {
                    Text(s.label).foregroundStyle(s.isBuy ? Theme.up : Theme.down)
                    Text("· " + Self.monthDay(s.displayTime)).foregroundStyle(Theme.textPrimary)
                    Image(systemName: s.confirmed ? "checkmark.circle.fill" : "circle.dashed")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                        .accessibilityLabel(s.confirmed ? L("已确认") : L("未确认"))
                }
                .font(.subheadline.weight(.bold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            } else if newerCandidate == nil {
                Text(L("暂无")).font(.subheadline.weight(.bold)).foregroundStyle(Theme.textSecondary)
            }
            if let c = newerCandidate {
                Text(L("待确认 %@ · %@", c.label, Self.monthDay(c.displayTime)))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
    }

    /// 「2026-09-19」或「2026-09-19 10:30」→「09-19」。
    static func monthDay(_ time: String) -> String {
        let day = time.prefix(10)
        return day.count == 10 ? String(day.suffix(5)) : String(day)
    }

    // MARK: - 大白话

    /// 标题旁的补充词。有方向时由箭头表达、不再写「结构偏强 / 偏弱」（那是买卖导向词，
    /// 也容易和图上的买卖点混淆）；没有方向（中枢形成 / 震荡）写「震荡中」。
    static func structureWord(_ phase: PivotPhase) -> String? {
        guard let d = phase.direction, d == "up" || d == "down" else { return L("震荡中") }
        return nil
    }

    /// 图例：三种样式各是什么，写在结论卡底部，第一次看的人不用猜红绿是什么意思。
    private var legend: some View {
        HStack(spacing: 12) {
            HStack(spacing: 4) {
                Circle().fill(Theme.up).frame(width: 7, height: 7)
                Circle().fill(Theme.down).frame(width: 7, height: 7)
                Text(L("已成立买卖点"))
            }
            HStack(spacing: 4) {
                Circle()
                    .strokeBorder(Theme.textSecondary, style: StrokeStyle(lineWidth: 1, dash: [2, 1.5]))
                    .frame(width: 8, height: 8)
                Text(L("待确认，不算买卖点"))
            }
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 2).fill(Theme.accent).frame(width: 8, height: 8)
                Text(L("标题为结构描述"))
            }
            Spacer(minLength: 0)
        }
        .font(.system(size: 10))
        .foregroundStyle(Theme.textSecondary)
        .lineLimit(1)
        .minimumScaleFactor(0.8)
    }

    /// 一句人话：说清价格和中枢的关系。叫法与流程图、后端阶段文案同一套（中枢、离开中枢、
    /// 回落 / 反弹、中枢上沿 / 下沿），不出现 ZG / ZD。
    static func plainSentence(_ phase: PivotPhase) -> String {
        let hi = format(phase.pivot.zg), lo = format(phase.pivot.zd)
        let up = phase.direction == "up"
        switch phase.phase {
        case "pivot_forming":
            return L("三段走势重叠，形成中枢（%@ ~ %@）", lo, hi)
        case "pivot_oscillating":
            return L("价格在中枢（%@ ~ %@）内反复，方向未明", lo, hi)
        case "leaving":
            return up ? L("价格向上离开中枢（上沿 %@），等待回落确认", hi)
                      : L("价格向下离开中枢（下沿 %@），等待反弹确认", lo)
        case "retrace_confirmed":
            if phase.outcome == "type2" {
                return up ? L("向上离开中枢后回落，回到中枢内但没有跌破下沿 %@", lo)
                          : L("向下离开中枢后反弹，回到中枢内但没有升破上沿 %@", hi)
            }
            return up ? L("向上离开中枢后回落，没有跌回中枢（%@ ~ %@）", lo, hi)
                      : L("向下离开中枢后反弹，没有升回中枢（%@ ~ %@）", lo, hi)
        case "divergence_turn":
            return up ? L("上涨段出现趋势背驰：价格创新高，但离开中枢这一段的 MACD 面积比前一段小")
                      : L("下跌段出现趋势背驰：价格创新低，但离开中枢这一段的 MACD 面积比前一段小")
        default:
            return L("价格与中枢（%@ ~ %@）的关系见下方说明", lo, hi)
        }
    }

    private static func format(_ v: Double) -> String {
        v >= 100 ? String(format: "%.0f", v) : String(format: "%.2f", v)
    }
}
