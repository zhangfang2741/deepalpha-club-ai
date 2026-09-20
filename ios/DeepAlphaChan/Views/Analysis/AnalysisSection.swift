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
