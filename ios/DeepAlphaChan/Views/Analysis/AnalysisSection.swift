import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 这张卡回答缠论用户翻开一只票时最先想知道的三件事，按「走势 → 结构 → 信号」
/// 从大到小铺开，每块都只陈述算法从 K 线里读出的事实、不替用户下操作结论：
///
/// - **走势**：缠论按**中枢排布**定义的大级别走势（`walk_type`）+ 延续/转折展望
///   （`trend_outlook`，由走势 + 终结性背驰派生）。这两者天然自洽。
/// - **结构**：当前中枢（多空争夺区）ZG/ZD 区间 + 现价在其上方/内部/下方，
///   以及笔（短期）/ 线段（中期）方向是否共振——多级别分开讲清楚，是缠论的读法，
///   不是自相矛盾。
/// - **信号**：最近一个买卖点（级别 / 强度 / 是否确认 / 价位）+ 背驰状态；完整
///   买卖点列表在「买卖点」独立 tab。
///
/// 顶部保留一句 `narrative.headline` 白话概括当引子（结构没成形时退回后端 summary）。
///
/// 刻意**不再**堆那串「多因子加权依据」：那些单条依据彼此方向相反（卡里都得挂
/// 一句"下列依据可能与结论相反"），用户反馈这种自相矛盾比没有更糟。现在换成上面
/// 三块层次分明、各自单一口径的事实，谁强谁弱、在哪个位置、有没有信号一目了然。
///
/// 风险提示已拆到 `RiskSection` 独立成一个 tab（见 ResultSegments）。
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        statusCard
    }

    // MARK: - 主卡

    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 16) {
                // 一句话白话概括（结构没成形时退回后端 summary）
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                Divider().overlay(Theme.border)

                trendBlock
                structureBlock
                signalBlock

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - 走势

    private var trendBlock: some View {
        factBlock(L("走势")) {
            HStack(spacing: 6) {
                Chip(text: SignalFormatting.walkTypeLabel(analysis.walkType),
                     color: SignalFormatting.walkTypeColor(analysis.walkType))
                Chip(text: SignalFormatting.trendOutlookLabel(analysis.trendOutlook),
                     color: SignalFormatting.trendOutlookColor(analysis.trendOutlook))
            }
            Text(SignalFormatting.walkTypeDetail(analysis.walkType))
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
    }

    // MARK: - 结构

    private var structureBlock: some View {
        factBlock(L("结构")) {
            VStack(alignment: .leading, spacing: 5) {
                infoLine(pivotLine)
                if let rhythm = rhythmLine { infoLine(rhythm) }
            }
        }
    }

    /// 当前中枢（多空争夺区）+ 现价所处位置。没有中枢时说明未成形。
    private var pivotLine: String {
        guard let p = analysis.strokePivots.last,
              let close = analysis.mergedCandles.last?.close else {
            return L("尚未形成中枢（单边推进或数据不足）")
        }
        let range = "\(fmt(p.zd))–\(fmt(p.zg))"
        if close > p.zg {
            return L("中枢 %1$@｜现价 %2$@ 站在中枢上方，多方暂占优", range, fmt(close))
        }
        if close < p.zd {
            return L("中枢 %1$@｜现价 %2$@ 跌破中枢下沿，空方暂占优", range, fmt(close))
        }
        return L("中枢 %1$@｜现价 %2$@ 在中枢内来回，多空僵持", range, fmt(close))
    }

    /// 笔（短期）/ 线段（中期）方向，及是否同向共振。
    private var rhythmLine: String? {
        let s = analysis.strokes.last?.direction
        let g = analysis.segments.last?.direction
        guard s != nil || g != nil else { return nil }
        let sTxt = s.map { $0 == .up ? L("笔向上") : L("笔向下") } ?? L("笔未成形")
        let gTxt = g.map { $0 == .up ? L("线段向上") : L("线段向下") } ?? L("线段未成形")
        if let s = s, let g = g {
            let note = s == g ? L("短期与中期同向") : L("短期与中期方向不一致")
            return L("%1$@ · %2$@（%3$@）", sTxt, gTxt, note)
        }
        return L("%1$@ · %2$@", sTxt, gTxt)
    }

    // MARK: - 信号

    private var signalBlock: some View {
        factBlock(L("买卖信号")) {
            VStack(alignment: .leading, spacing: 6) {
                latestSignalRow
                infoLine(divergenceNote)
                if analysis.signals.count > 1 {
                    Text(L("共 %lld 个买卖点，完整列表见「买卖点」标签", analysis.signals.count))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
            }
        }
    }

    /// 最近一个买卖点（时间倒序取首个）——级别 / 强度 / 是否确认 / 价位。
    @ViewBuilder
    private var latestSignalRow: some View {
        if let sig = analysis.signals.sorted(by: { $0.time > $1.time }).first {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(sig.label)
                        .font(.subheadline.bold())
                        .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
                    Chip(text: SignalFormatting.strengthLabel(sig.strength),
                         color: SignalFormatting.strengthColor(sig.strength))
                    if !sig.confirmed { Chip(text: L("未确认·左侧预判"), color: Theme.textSecondary) }
                    Spacer(minLength: 4)
                    Text(sig.time).font(.caption).foregroundColor(Theme.textSecondary)
                }
                Text(L("价位 %@", fmt(sig.price)))
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            }
        } else {
            Text(L("近期无买卖点信号"))
                .font(AnalysisType.body)
                .foregroundColor(Theme.textSecondary)
        }
    }

    /// 背驰状态：由 trend_outlook 的转折分支反推（reversal 才是终结性背驰），
    /// 单一口径，不跟走势块打架。
    private var divergenceNote: String {
        switch analysis.trendOutlook ?? "" {
        case "reversal_down": return L("顶背驰：价创新高但动能没跟上，上涨力度在衰减")
        case "reversal_up": return L("底背驰：价创新低但动能在减弱，下跌力度在衰减")
        default: return L("暂无背驰信号，力度未见明显衰减")
        }
    }

    // MARK: - 结构统计

    /// 一行精简结构统计。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    // MARK: - 复用小组件

    /// 段内小标题（走势 / 结构 / 信号）+ 内容。
    private func factBlock<Content: View>(
        _ title: String, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(AnalysisType.label)
                .tracking(0.5)
                .foregroundColor(Theme.textSecondary)
            content()
        }
    }

    private func infoLine(_ text: String) -> some View {
        Text(text)
            .font(AnalysisType.body)
            .foregroundColor(Theme.textPrimary)
            .lineSpacing(3)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func fmt(_ v: Double) -> String { String(format: "%.2f", v) }
}
