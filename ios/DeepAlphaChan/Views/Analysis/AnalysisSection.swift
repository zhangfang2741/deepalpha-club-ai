import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 目标从「把结果画出来」升级成「让用户看懂**为什么这样判断**」，但保持紧凑：
///
/// - **综合判断**（默认显示）：一句话同时给出大结构（线段方向）、小结构（最新笔
///   方向）、所处位置（中枢内 / 上方 / 下方）、信号状态（确认 / 候选 / 暂无）——
///   全部由结构数据拼出，不写死文案。
/// - **走势** chips：中枢级别走势（`walk_type`）+ 延续/转折展望（`trend_outlook`）。
/// - **查看判断依据**（默认收起）：展开才显示「笔 / 线段 / 中枢 / 买卖点」的证据链
///   表格——每一行给「当前结果 + 判断依据」。这张表是核心教学：让用户明白一根
///   向上笔为什么不等于趋势反转。收起时不占地方，避免首屏太密。
///
/// 依据文案由 `ChanEvidence` 从结构数据规则化推导（对齐 `narrative.py` 的思路，
/// 但在端上、离线、即时）。刻意不再堆易自相矛盾的「多因子加权依据」。
/// 风险提示在 `RiskSection` 独立 tab；字号走 AnalysisType 三级（见 SignalFormatting）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    @State private var showEvidence = false

    var body: some View {
        statusCard
    }

    // MARK: - 主卡

    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 综合判断：结构没成形时退回后端白话/摘要
                Text(ChanEvidence.verdict(analysis) ?? analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                progressBlock

                Divider().overlay(Theme.border)
                trendBlock

                Divider().overlay(Theme.border)
                evidenceDisclosure

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

    // MARK: - 走到哪一步（走势阶段）

    private var progressBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(L("走到哪一步"))
                    .font(AnalysisType.label).tracking(0.5)
                    .foregroundColor(Theme.textSecondary)
                Spacer(minLength: 8)
                Chip(text: ChanPhase.stageLabel(analysis), color: Theme.segment)
            }
            VStack(alignment: .leading, spacing: 9) {
                ForEach(ChanPhase.steps(analysis)) { step in stepRow(step) }
            }
            // 为什么就在这一步：把判断依据贴进阶段本身，而不是丢到另一个折叠区
            HStack(alignment: .top, spacing: 6) {
                Text(L("因为")).font(.caption2.weight(.semibold)).foregroundColor(Theme.accent)
                Text(ChanPhase.reason(analysis))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let branches = ChanPhase.branches(analysis) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(branches.enumerated()), id: \.offset) { _, b in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "arrow.triangle.branch")
                                .font(.system(size: 10)).foregroundColor(Theme.segment)
                                .frame(width: 14)
                            Text(b).font(.caption2).foregroundColor(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .padding(9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func stepRow(_ step: PhaseStep) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: step.state.symbol)
                .font(.system(size: 13))
                .foregroundColor(step.state.color)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 1) {
                Text(step.state.label)
                    .font(.system(size: 9, weight: .semibold)).tracking(0.5)
                    .foregroundColor(step.state.color)
                Text(step.text)
                    .font(.footnote)
                    .foregroundColor(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: - 证据链（可折叠）

    private var evidenceDisclosure: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { showEvidence.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "checklist").foregroundColor(Theme.accent).font(.footnote)
                    Text(L("查看判断依据"))
                        .font(.footnote.weight(.semibold))
                        .foregroundColor(Theme.textPrimary)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Theme.textSecondary)
                        .rotationEffect(.degrees(showEvidence ? 0 : -90))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if showEvidence {
                VStack(spacing: 10) {
                    ForEach(ChanEvidence.rows(analysis)) { row in evidenceRow(row) }
                }
                if let tip = ChanEvidence.tip(analysis) {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "lightbulb").font(.caption2).foregroundColor(Theme.segment)
                        Text(tip)
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    private func evidenceRow(_ row: EvidenceRow) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(row.term)
                .font(.footnote.bold())
                .foregroundColor(row.termColor)
                .frame(width: 40, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(row.result)
                    .font(.footnote.weight(.semibold))
                    .foregroundColor(Theme.textPrimary)
                Text(row.why)
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - 结构统计

    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    // MARK: - 复用小组件

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
}

// MARK: - 证据链推导

/// 证据链的一行：结构名 + 当前结果 + 判断依据。
struct EvidenceRow: Identifiable {
    let id = UUID()
    let term: String
    let termColor: Color
    let result: String
    let why: String
}

/// 把 ChanAnalysis 的结构数据规则化成「为什么这样判断」的证据链与一句话综合判断。
///
/// 全部由数据推导、不写死场景文案——否则又会退回「描述没价值」。放在这里而不是
/// 后端，是为了即时、离线、免一次网络往返（与 SignalFormatting 同层）。
enum ChanEvidence {

    /// 一句话综合判断：大结构（线段）+ 小结构（笔）+ 位置（中枢）+ 信号状态。
    /// 结构还没成形（没有笔）时返回 nil，由调用方退回后端白话。
    static func verdict(_ a: ChanAnalysis) -> String? {
        guard let bi = a.strokes.last?.direction else { return nil }
        let segDir = a.segments.last?.direction
        let segPart: String
        if segDir == .up { segPart = L("向上线段") }
        else if segDir == .down { segPart = L("向下线段") }
        else { segPart = L("尚未成形的线段") }
        let biPart = bi == .up ? L("向上笔") : L("向下笔")
        return L("当前处于%1$@中的一根%2$@，%3$@，%4$@。",
                 segPart, biPart, positionPhrase(a), signalPhrase(a))
    }

    /// 现价相对最近中枢的位置短语（含中枢是否延伸）。
    private static func positionPhrase(_ a: ChanAnalysis) -> String {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else {
            return L("尚未形成中枢")
        }
        let pos: String
        if close > p.zg { pos = L("现价站上中枢上方") }
        else if close < p.zd { pos = L("现价跌破中枢下沿") }
        else { pos = L("现价在中枢内") }
        return p.confirmed ? pos : L("%@、中枢仍在延伸", pos)
    }

    /// 最近买卖点状态短语。
    private static func signalPhrase(_ a: ChanAnalysis) -> String {
        guard let s = a.signals.sorted(by: { $0.time > $1.time }).first else {
            return L("暂无确认买卖点")
        }
        let state = s.confirmed ? L("已确认") : L("候选")
        return L("最近出现%1$@（%2$@）", s.label, state)
    }

    /// 证据链四行：笔 / 线段 / 中枢 / 买卖点。
    static func rows(_ a: ChanAnalysis) -> [EvidenceRow] {
        [stroke(a), segment(a), pivot(a), signal(a)]
    }

    private static func stroke(_ a: ChanAnalysis) -> EvidenceRow {
        let result: String
        let why: String
        if let s = a.strokes.last {
            let dir = s.direction == .up ? L("向上笔") : L("向下笔")
            result = s.confirmed ? L("%@已走完", dir) : L("%@形成中", dir)
            if s.confirmed {
                why = L("两端分型已确认，这一笔已经走完")
            } else if s.direction == .up {
                why = L("最新底分型后向上延伸，顶分型尚未确认")
            } else {
                why = L("最新顶分型后向下延伸，底分型尚未确认")
            }
        } else {
            result = L("尚未成形")
            why = L("有效分型不足，还连不成一笔")
        }
        return EvidenceRow(term: L("笔"), termColor: Theme.stroke, result: result, why: why)
    }

    private static func segment(_ a: ChanAnalysis) -> EvidenceRow {
        let result: String
        let why: String
        if let s = a.segments.last {
            let dir = s.direction == .up ? L("向上线段") : L("向下线段")
            result = s.confirmed ? L("%@已结束", dir) : L("%@未结束", dir)
            why = s.confirmed
                ? L("特征序列已确认线段结束")
                : L("当前笔尚未破坏线段结构，线段延续")
        } else {
            result = L("尚未成形")
            why = L("不足 3 笔，还叠不出线段")
        }
        return EvidenceRow(term: L("线段"), termColor: Theme.segment, result: result, why: why)
    }

    private static func pivot(_ a: ChanAnalysis) -> EvidenceRow {
        let result: String
        let why: String
        if let p = a.strokePivots.last {
            result = p.confirmed ? L("中枢已确认") : L("中枢延伸中")
            if let close = a.mergedCandles.last?.close, close > p.zg || close < p.zd {
                why = L("走势已离开 %1$@–%2$@ 区间，等待是否回抽",
                        fmt(p.zd), fmt(p.zg))
            } else {
                why = L("最新走势仍与 %1$@–%2$@ 区间重叠", fmt(p.zd), fmt(p.zg))
            }
        } else {
            result = L("尚未形成中枢")
            why = L("重叠不足三段，还没围出中枢")
        }
        return EvidenceRow(term: L("中枢"), termColor: Theme.pivotFill, result: result, why: why)
    }

    private static func signal(_ a: ChanAnalysis) -> EvidenceRow {
        let result: String
        let why: String
        if let s = a.signals.sorted(by: { $0.time > $1.time }).first {
            result = s.confirmed ? L("%@已确认", s.label) : L("%@候选", s.label)
            why = s.confirmed
                ? L("离开与回抽结构均已完成确认")
                : L("落在未确认笔上，属左侧预判")
        } else {
            result = L("暂无确认信号")
            why = L("尚未完成离开段与回抽结构")
        }
        return EvidenceRow(term: L("买卖点"), termColor: Theme.accent, result: result, why: why)
    }

    /// 教学点睛：仅当笔与线段方向相反（短期反抽大级别）时才提示，其余情形不啰嗦。
    static func tip(_ a: ChanAnalysis) -> String? {
        guard let bi = a.strokes.last?.direction,
              let seg = a.segments.last?.direction, bi != seg else { return nil }
        return bi == .up
            ? L("一根向上笔 ≠ 趋势反转：线段未被破坏前，它只是下降线段里的一次反抽。")
            : L("一根向下笔 ≠ 趋势结束：线段未被破坏前，它只是上升线段里的一次回调。")
    }

    private static func fmt(_ v: Double) -> String { String(format: "%.2f", v) }
}

// MARK: - 走势阶段（走到哪一步）

/// 单步的状态：已完成 / 进行中 / 待确认。
enum PhaseState {
    case done, doing, wait

    var symbol: String {
        switch self {
        case .done: return "checkmark.circle.fill"
        case .doing: return "circle.fill"
        case .wait: return "circle"
        }
    }
    var color: Color {
        switch self {
        case .done: return Theme.accent
        case .doing: return Theme.accent
        case .wait: return Theme.textSecondary
        }
    }
    var label: String {
        switch self {
        case .done: return L("已完成")
        case .doing: return L("进行中")
        case .wait: return L("待确认")
        }
    }
}

/// 走势阶段的一步。
struct PhaseStep: Identifiable {
    let id = UUID()
    let state: PhaseState
    let text: String
}

/// 用中枢生命周期把「走到哪一步」推导出来：中枢形成 → 震荡/离开 → 回抽确认，
/// 并给出下一步的可能分支。端上规则化推导（与 ChanEvidence 同口径），后续要更严格
/// 的离开段/回抽判定可整体挪到后端 pivot_phase。
enum ChanPhase {

    /// 阶段总标签（放在小节右侧的 chip）。
    static func stageLabel(_ a: ChanAnalysis) -> String {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else {
            return L("中枢未形成")
        }
        if close > p.zg { return L("向上离开中枢") }
        if close < p.zd { return L("向下离开中枢") }
        return L("中枢震荡阶段")
    }

    /// 已完成 / 进行中 / 待确认 的步骤序列。
    static func steps(_ a: ChanAnalysis) -> [PhaseStep] {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else {
            return [
                PhaseStep(state: .doing, text: L("走势单边推进，尚未围出中枢")),
                PhaseStep(state: .wait, text: L("出现三段重叠后才形成中枢")),
            ]
        }
        var steps: [PhaseStep] = [
            PhaseStep(state: .done, text: L("形成中枢（%1$@–%2$@）", fmt(p.zd), fmt(p.zg)))
        ]
        if close > p.zg {
            steps.append(PhaseStep(state: .done, text: L("向上离开中枢（现价站上 ZG %@）", fmt(p.zg))))
            steps.append(hasConfirmed(a, "buy3")
                ? PhaseStep(state: .done, text: L("回抽不进中枢，三买确认"))
                : PhaseStep(state: .wait, text: L("等待离开段走完后回抽确认")))
        } else if close < p.zd {
            steps.append(PhaseStep(state: .done, text: L("向下离开中枢（现价跌破 ZD %@）", fmt(p.zd))))
            steps.append(hasConfirmed(a, "sell3")
                ? PhaseStep(state: .done, text: L("反抽不回中枢，三卖确认"))
                : PhaseStep(state: .wait, text: L("等待反抽确认")))
        } else {
            steps.append(PhaseStep(state: .doing, text: L("中枢内震荡，区间延伸中")))
            steps.append(PhaseStep(state: .wait, text: L("等待向上突破 ZG 或跌破 ZD")))
        }
        return steps
    }

    /// 为什么当前就在这一步：给出决定阶段的那条结构依据（贴进阶段，回答「原因」）。
    static func reason(_ a: ChanAnalysis) -> String {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else {
            return L("走势还在单边推进，三段没重叠，围不出中枢。")
        }
        if close > p.zg {
            return L("现价 %1$@ 已站上 ZG %2$@，最新向上笔离开了中枢区间。", fmt(close), fmt(p.zg))
        }
        if close < p.zd {
            return L("现价 %1$@ 已跌破 ZD %2$@，最新向下笔离开了中枢区间。", fmt(close), fmt(p.zd))
        }
        return L("现价 %1$@ 仍在 %2$@–%3$@ 区间内反复重叠，中枢在延伸。",
                 fmt(close), fmt(p.zd), fmt(p.zg))
    }

    /// 下一步的可能分支（两条），已确认到位时返回 nil。
    static func branches(_ a: ChanAnalysis) -> [String]? {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else { return nil }
        if close > p.zg {
            if hasConfirmed(a, "buy3") { return nil }
            return [L("回抽不进中枢 → 确认三买"), L("回抽跌回中枢 → 回到震荡")]
        }
        if close < p.zd {
            if hasConfirmed(a, "sell3") { return nil }
            return [L("反抽不回中枢 → 确认三卖"), L("反抽升回中枢 → 回到震荡")]
        }
        return [L("向上突破 ZG → 进入上涨离开段"), L("向下跌破 ZD → 进入下跌离开段")]
    }

    private static func hasConfirmed(_ a: ChanAnalysis, _ type: String) -> Bool {
        a.signals.contains { $0.type.rawValue == type && $0.confirmed }
    }

    private static func fmt(_ v: Double) -> String { String(format: "%.2f", v) }
}
