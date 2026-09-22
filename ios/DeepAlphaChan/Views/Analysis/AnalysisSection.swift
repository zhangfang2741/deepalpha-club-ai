import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 刻意不叫「形态分析」：这里只陈述算法从 K 线结构里读出的事实（形态处在哪个阶段、
/// 各维度的技术强弱如何加权），不给任何投资结论，条件页的风险提示也写明「不要只看
/// 技术信号，要结合整体走势与市场结构」——这张卡本身就是那个「整体」的呈现，标题得
/// 对上，不能听起来像只在讲局部形态。
///
/// 不展示"加权强弱结论"的多空 chip（`recommendation.bias`）：它和大白话摘要、
/// 走势展望的算法口径各自独立，同一次分析里出现过互相矛盾的情况（比如结论行写
/// "下跌动能转弱"、走势展望却说"上涨延续"），用户反馈这种自相矛盾比"没有结论"
/// 更糟，所以这个多空结论至今没有入口。
///
/// 「走势」区块（`walkTypeSection`）展示的 `walk_type`/`trend_outlook` 是另一
/// 回事：这两个是纯几何判定（中枢排布 + 背驰方向），不是多因子加权，口径单一、
/// 不会自相矛盾，因此可以直接展示——不要和上面那条"不展示方向性判断"的原则
/// 混为一谈。
///
/// 风险提示已拆到 `RiskSection` 独立成一个 tab（见 ResultSegments）。
///
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        statusCard
    }

    /// 大白话摘要按关键词着色（笔/线段/中枢/背驰/买卖点）。优先用
    /// `structureHeadline`——它和下面「查看判断依据」展开的四层结论出自同一份
    /// 判定（线段/笔方向、中枢位置、最新买卖点），是同一套事实的两种呈现；
    /// 结构没成形到能拼出这句话时（缺线段或缺笔）才退回 `narrative.headline`，
    /// 两者都没有时最后退回后端兜底摘要 `analysis.summary`（不做着色处理）。
    private var headlineText: Text {
        if let headline = analysis.structureHeadline ?? analysis.narrative?.headline {
            return Text(HeadlineHighlighter.highlight(headline))
        }
        return Text(analysis.summary)
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    /// 当前状态：大白话一句话 → 走到哪一步 → 走势标签 → 查看判断依据（默认收起）
    /// → 结构统计，只陈述事实不下结论。
    ///
    /// 卡片本身不可折叠（`SectionCard` 而不是 `CollapsibleCard`）：这是
    /// 「整体分析」这个独立 tab 的主内容，不是可有可无的附加信息，折叠起来
    /// 一进页面就看不到东西没有意义。「查看判断依据」这一小块内部单独收起——
    /// 加权依据是给想深挖的人看的，默认展开会和「走到哪一步」的结论抢视觉焦点。
    private var statusCard: some View {
        SectionCard(title: L("当前状态"), systemImage: "waveform.path.ecg") {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要；关键词着色见
                // HeadlineHighlighter，未命中关键词的字保持默认前景色
                headlineText
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let phase = analysis.pivotPhase {
                    Divider().overlay(Theme.border)
                    PivotPhaseBlock(phase: phase)
                }

                if analysis.walkType != nil || analysis.trendOutlook != nil {
                    Divider().overlay(Theme.border)
                    walkTypeSection
                }

                if !analysis.structureLayers.isEmpty {
                    Divider().overlay(Theme.border)
                    reasonsDisclosure(analysis.structureLayers)
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 「走势」区块：短标签 chip（上涨趋势/可能转折向下…）+ 一行补充说明
    /// （中枢依次抬高…）。后端的 `walkTypeLabel`/`trendOutlookLabel` 是完整句子
    /// （给 summary 拼句子用），塞进 chip 里会太长，这里按原始枚举码单独映射一套
    /// 短文案——短标签只在这一处使用，暂不值得为此新增后端字段。
    private var walkTypeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("走势"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            HStack(spacing: 8) {
                if let walkType = analysis.walkType {
                    Chip(text: WalkTypeFormatting.shortLabel(walkType, fallback: analysis.walkTypeLabel),
                         color: Theme.accent)
                }
                if let outlook = analysis.trendOutlook {
                    Chip(text: WalkTypeFormatting.shortOutlookLabel(outlook, fallback: analysis.trendOutlookLabel),
                         color: Theme.segment)
                }
            }
            if let walkType = analysis.walkType, let detail = WalkTypeFormatting.detail(walkType) {
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
    }

    /// 「查看判断依据」：默认收起，按笔/线段/中枢/买卖点分层展示当前状态
    /// （而不是一份扁平的加权依据列表）——用户想知道结论怎么来的，按结构层
    /// 拆开比一句句读加权因子更好懂。
    private func reasonsDisclosure(_ layers: [StructureLayer]) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(layers) { layer in
                    StructureLayerRow(layer: layer)
                }
            }
            .padding(.top, 6)
        } label: {
            Label(L("查看判断依据"), systemImage: "checklist")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
        }
        .tint(Theme.textSecondary)
    }
}

/// 「查看判断依据」里的一行：结构层色标 + 当前状态标题 + 说明。
private struct StructureLayerRow: View {
    let layer: StructureLayer

    /// 层级色标复用图表图层图例色（笔=蓝/线段=橙/中枢=紫），买卖点用主题蓝——
    /// 这里是纯粹的「给类别贴标签」，和大白话摘要的语义着色（HeadlineHighlighter）
    /// 是两码事，不要混用同一套规则。
    private var color: Color {
        switch layer.layer {
        case "stroke": return Theme.stroke
        case "segment": return Theme.segment
        case "pivot": return Theme.pivotFill
        case "signal": return Theme.accent
        default: return Theme.textSecondary
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(layer.label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(color)
                .frame(width: 40, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(layer.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                Text(layer.detail)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// 「走到哪一步」区块：阶段徽标（点击弹讲解）+ checklist + 因为 + 分支说明。
///
/// 独立成子 View 而不是 AnalysisSection 的私有方法：需要自己的 @State 管理
/// 讲解 sheet 的呈现，方法内部不能声明 @State。
private struct PivotPhaseBlock: View {
    let phase: PivotPhase
    @State private var showGuide = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Text(L("走到哪一步"))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Button {
                    showGuide = true
                } label: {
                    HStack(spacing: 4) {
                        Text(phase.phaseLabel)
                        Image(systemName: "info.circle")
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Theme.pivotPhaseColor(phase.phase).opacity(0.15))
                .foregroundColor(Theme.pivotPhaseColor(phase.phase))
                .clipShape(Capsule())
                .accessibilityHint(L("点击查看阶段判定说明"))
            }

            // 字号对齐「查看判断依据」里 StructureLayerRow 的 title(14 semibold)/
            // detail(.caption)——同一张卡片里两处列表项该是一样的字号层级。
            VStack(alignment: .leading, spacing: 6) {
                ForEach(phase.checklist) { item in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: item.state == .done ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(item.state == .done ? Theme.accent : Theme.textSecondary)
                            .font(.system(size: 14))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.label)
                                .font(.system(size: 14, weight: item.state == .done ? .semibold : .regular))
                                .foregroundColor(item.state == .done ? Theme.textPrimary : Theme.textSecondary)
                            if !item.detail.isEmpty {
                                Text(item.detail)
                                    .font(.caption)
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                    }
                }
            }

            HStack(alignment: .top, spacing: 4) {
                Text(L("因为")).font(.caption).foregroundColor(Theme.accent)
                Text(phase.reason).font(.caption).foregroundColor(Theme.textSecondary)
            }

            // 套一层和 StructureLayerRow 一样的卡片背景，和「查看判断依据」的
            // 视觉分量对齐——之前直接铺在卡片背景上，分支说明和上面的正文
            // 文字混在一起，看不出这是独立的一块信息。箭头图标也换成在小
            // 尺寸下依然清晰的样式（原来的 arrow.turn.down.right 在 10pt 太小
            // 几乎看不清）。
            if !phase.branches.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(phase.branches) { branch in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "arrowshape.turn.up.right.fill")
                                .font(.system(size: 11))
                                .foregroundColor(Theme.accent)
                            Text("\(branch.conditionLabel) → \(branch.resultLabel)")
                                .font(.caption)
                                .foregroundColor(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .sheet(isPresented: $showGuide) {
            NavigationStack { PivotPhaseGuideSheet(pivotPhase: phase) }
                .preferredColorScheme(.dark)
        }
    }
}
