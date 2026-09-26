import SwiftUI

/// 详情页最上方的结论卡：第一眼回答「现在什么状态、最新信号是什么、次级别怎么说」。
///
/// 以前这些答案压在图表 + MACD + 图例 + 三个 Tab 之后，第一屏看不到结论。阶段标题的
/// 颜色与自选列表的状态标签同一套（Theme.phaseColor）；一句话解读由阶段 + 方向在端上生成，
/// 只描述结构本身，不给操作建议。
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
                    Text(phase.phaseLabel)
                        .font(.system(size: 21, weight: .heavy))
                        .foregroundStyle(tint)
                    Text(Self.structureWord(phase))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint.opacity(0.85))
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

    private var latestSignal: Signal? { analysis.signals.max { $0.time < $1.time } }

    private var latestSignalTile: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(L("最新信号")).font(.caption2).foregroundStyle(Theme.textSecondary)
            if let s = latestSignal {
                HStack(spacing: 4) {
                    Text(s.label).foregroundStyle(s.isBuy ? Theme.up : Theme.down)
                    Text("· " + Self.monthDay(s.time)).foregroundStyle(Theme.textPrimary)
                    Image(systemName: s.confirmed ? "checkmark.circle.fill" : "circle.dashed")
                        .font(.caption2)
                        .foregroundStyle(s.confirmed ? Theme.down : Theme.textSecondary)
                        .accessibilityLabel(s.confirmed ? L("已确认") : L("未确认"))
                }
                .font(.subheadline.weight(.bold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            } else {
                Text(L("暂无")).font(.subheadline.weight(.bold)).foregroundStyle(Theme.textSecondary)
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

    /// 偏多 / 偏空 / 中性，与 Theme.phaseColor 同一判断（背驰转折时方向取反）。
    static func bias(_ phase: PivotPhase) -> Int {
        guard let d = phase.direction, d == "up" || d == "down" else { return 0 }
        return (d == "up") != (phase.phase == "divergence_turn") ? 1 : -1
    }

    static func structureWord(_ phase: PivotPhase) -> String {
        switch bias(phase) {
        case 1: return L("结构偏强")
        case -1: return L("结构偏弱")
        default: return L("震荡中")
        }
    }

    /// 一句人话：说清价格和震荡区（中枢）的关系，数字取中枢上下沿，不出现 ZG / ZD。
    static func plainSentence(_ phase: PivotPhase) -> String {
        let hi = format(phase.pivot.zg), lo = format(phase.pivot.zd)
        let up = phase.direction == "up"
        switch phase.phase {
        case "pivot_forming":
            return L("价格开始在 %@ ~ %@ 之间来回，正在形成震荡区", lo, hi)
        case "pivot_oscillating":
            return L("价格还在 %@ ~ %@ 的震荡区里来回，方向未明", lo, hi)
        case "leaving":
            return up ? L("价格向上离开 %@ ~ %@ 的震荡区，等回落确认", lo, hi)
                      : L("价格向下离开 %@ ~ %@ 的震荡区，等反弹确认", lo, hi)
        case "retrace_confirmed":
            return up ? L("突破震荡区后回落，没有跌回区间（%@ ~ %@）", lo, hi)
                      : L("跌破震荡区后反弹，没有回到区间（%@ ~ %@）", lo, hi)
        case "divergence_turn":
            return up ? L("继续上涨但力度变弱，上涨可能接近尾声")
                      : L("继续下跌但力度变弱，下跌可能接近尾声")
        default:
            return L("价格与 %@ ~ %@ 震荡区的关系见下方说明", lo, hi)
        }
    }

    private static func format(_ v: Double) -> String {
        v >= 100 ? String(format: "%.0f", v) : String(format: "%.2f", v)
    }
}
