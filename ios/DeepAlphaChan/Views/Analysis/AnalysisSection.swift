import SwiftUI

/// 从当前事实出发，依次解释结构位置、判断依据和待观察条件。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            SectionCard(title: L("现在处于什么状态"), systemImage: "waveform.path.ecg") {
                Text(HeadlineHighlighter.highlight(
                    analysis.structureHeadline ?? analysis.narrative?.headline ?? analysis.summary
                ))
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
                .lineSpacing(5)
                .fixedSize(horizontal: false, vertical: true)

                if let walkType = analysis.walkType {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(L("区间走势：%@", WalkTypeFormatting.shortLabel(walkType, fallback: analysis.walkTypeLabel)))
                            .font(.subheadline.bold())
                            .foregroundStyle(WalkTypeFormatting.color(walkType))
                        if let detail = WalkTypeFormatting.detail(walkType) {
                            Text(detail).font(.subheadline).foregroundStyle(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                Text(L("以下状态对应当前图表周期与区间；切换周期后，结构与信号可能不同。"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let phase = analysis.pivotPhase {
                PivotPhaseBlock(phase: phase)
            } else {
                SectionCard(title: L("01 · 结构位置"), systemImage: "square.stack.3d.up") {
                    Text(L("当前数据尚不足以判断中枢阶段，请先对照图上的笔与线段。"))
                        .font(AnalysisType.body)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    AnalysisTermLink(term: "中枢", color: Theme.pivotFill)
                }
            }

            SectionCard(title: L("02 · 图上依据"), systemImage: "checklist") {
                if analysis.structureLayers.isEmpty {
                    Text(L("暂无分层判断依据，先观察结构是否形成。"))
                        .font(AnalysisType.body)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    // 先看大结构，再看局部笔和信号，与学习页的阅读顺序一致。
                    ForEach(orderedLayers) { layer in
                        StructureLayerRow(layer: layer)
                    }
                }
                Text(L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                       analysis.barsCount, analysis.strokes.count, analysis.segments.count,
                       analysis.strokePivots.count + analysis.segmentPivots.count, analysis.signals.count))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            SectionCard(title: L("03 · 接下来观察什么"), systemImage: "arrow.triangle.branch") {
                if let phase = analysis.pivotPhase {
                    ForEach(phase.checklist.filter { $0.state == .pending }) { item in
                        Label(item.label, systemImage: "circle.dashed")
                            .font(.subheadline.bold())
                            .foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        if !item.detail.isEmpty {
                            Text(item.detail).font(AnalysisType.body).foregroundStyle(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    ForEach(phase.branches) { branch in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(branch.conditionLabel)
                                .font(.subheadline.bold())
                                .foregroundStyle(Theme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(AnalysisInterpretation.branchExplanation(branch.outcome))
                                .font(AnalysisType.body)
                                .foregroundStyle(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
                    }
                }
                if let outlook = analysis.trendOutlook {
                    Text(WalkTypeFormatting.shortOutlookLabel(outlook, fallback: analysis.trendOutlookLabel))
                        .font(.subheadline.bold())
                        .foregroundStyle(WalkTypeFormatting.color(outlook))
                }
                Text(L("这些是后续观察条件，不代表已经发生。结构确认请看实线与虚线，具体信号请核对「买卖点」。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                AnalysisTermLink(term: "走势级别", color: Theme.textSecondary)
            }
        }
    }

    private var orderedLayers: [StructureLayer] {
        let order = ["segment", "pivot", "stroke", "signal"]
        return analysis.structureLayers.sorted {
            (order.firstIndex(of: $0.layer) ?? order.count) < (order.firstIndex(of: $1.layer) ?? order.count)
        }
    }
}
