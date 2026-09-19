import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 刻意不叫「形态分析」：这里只陈述算法从 K 线结构里读出的事实（形态处在哪个阶段、
/// 各维度的技术强弱如何加权），不给任何投资结论，条件页的风险提示也写明「不要只看
/// 技术信号，要结合整体走势与市场结构」——这张卡本身就是那个「整体」的呈现，标题得
/// 对上，不能听起来像只在讲局部形态。
///
/// 拆成两张卡而不是一张长卡：
/// - 当前状态：加权后的技术强弱 → 各项事实依据 → 一行结构统计，回答「现在是什么样」；
/// - 走势展望：延续/转折的结论单独放大呈现，回答「接下来大概率怎么走」——两个问题
///   读法不同，挤在同一张卡里，走势展望这句最该先读到的话反而被淹没在事实列表中间。
///
/// 风险提示已拆到 `RiskSection` 独立成一个 tab（见 ResultSegments），不再嵌在这里：
/// 折叠在整体分析卡片里时经常被当成结论的一部分顺手划过，与「陈述事实」混在一起读者
/// 分不清哪句是事实、哪句是「这些事实有多不可靠」。
///
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            statusCard
            outlookCard
        }
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    /// 走势展望（延续 vs 转折，缠论走势分类）：文案 + 图标 + 配色（复用多空色）。
    /// 结构没成形（trendOutlook 为空/unclear）时给一句待确认的中性文案，而不是
    /// 整张卡消失——两张卡并列时缺一张会显得布局跳来跳去。
    private var outlookInfo: (label: String, icon: String, color: Color) {
        guard let o = analysis.trendOutlook, o != "unclear" else {
            return (L("结构暂未成形，还需更多笔/线段确认后才能给出走势展望"),
                    "questionmark.circle", Theme.textSecondary)
        }
        switch o {
        case "reversal_up":
            return (L("出现转折信号，可能转为上涨（力度最强的买点结构）"),
                    "arrow.turn.right.up", SignalFormatting.biasColor("bullish"))
        case "reversal_down":
            return (L("出现转折信号，可能转为下跌"),
                    "arrow.turn.right.down", SignalFormatting.biasColor("bearish"))
        case "continuation_up":
            return (L("上涨延续"), "arrow.up.right", SignalFormatting.biasColor("bullish"))
        case "continuation_down":
            return (L("下跌延续"), "arrow.down.right", SignalFormatting.biasColor("bearish"))
        case "breakout_up":
            return (L("盘整向上突破，倾向转为上涨"),
                    "arrow.up.forward.circle", SignalFormatting.biasColor("bullish"))
        case "breakout_down":
            return (L("盘整向下突破，倾向转为下跌"),
                    "arrow.down.forward.circle", SignalFormatting.biasColor("bearish"))
        case "range":
            return (L("盘整延续（围绕中枢震荡）"),
                    "arrow.left.and.right", SignalFormatting.biasColor("neutral"))
        default:
            return (L("结构暂未成形，还需更多笔/线段确认后才能给出走势展望"),
                    "questionmark.circle", Theme.textSecondary)
        }
    }

    /// 标题栏 chip：优先用加权后的多空倾向；结构没成形时退回趋势。
    private var chip: (String, Color) {
        if let rec = analysis.recommendation {
            return (SignalFormatting.biasLabel(rec.bias), SignalFormatting.biasColor(rec.bias))
        }
        return (SignalFormatting.trendLabel(analysis.currentTrend),
                SignalFormatting.trendColor(analysis.currentTrend))
    }

    /// 当前状态：大白话一句话 → 加权后的技术强弱 → 各项事实依据 → 一行结构统计。
    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        accessoryChip: chip, defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let rec = analysis.recommendation {
                    // 技术强弱单独一行：它是各项事实的加权汇总，和下面逐条列出的
                    // 事实是两个层次，挨着排会混成一团。
                    Text(rec.actionLabel)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(SignalFormatting.biasColor(rec.bias))
                        .fixedSize(horizontal: false, vertical: true)

                    if !rec.reasons.isEmpty {
                        Divider().overlay(Theme.border)
                        // 首条是「几项偏多、几项偏空」的加权统计，先解释了为什么
                        // 下面会出现与上方强弱反向的单条事实
                        BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                    }
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 走势展望：不折叠，用大图标 + 渐变色块直接给出结论，一眼可读——这是继「当前
    /// 状态」之后用户最想看的一句话，不该像依据/统计那样藏在收起的卡片里。
    private var outlookCard: some View {
        let info = outlookInfo
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "binoculars.fill").foregroundColor(Theme.accent)
                Text(L("走势展望")).font(.headline).foregroundColor(Theme.textPrimary)
            }

            HStack(spacing: 14) {
                ZStack {
                    Circle().fill(info.color.opacity(0.15)).frame(width: 44, height: 44)
                    Image(systemName: info.icon)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundColor(info.color)
                }
                Text(info.label)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(info.color)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(colors: [info.color.opacity(0.12), Theme.surface],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14).stroke(info.color.opacity(0.25), lineWidth: 1)
        )
    }
}
