import SwiftUI

/// 结构位置全局判定图里能点开详情的单元——5 个状态方块 + 6 条判定边。
///
/// 这是全部可能结果的地图，不是必然依次完成的进度条：`build_pivot_phase()`
/// 每次都拿完整笔历史重新判一遍，直接给出属于这 5 个方块之一的结果，不依赖
/// 上一次的结论（见 app/services/chan/pivot_phase.py 顶部 docstring）。
enum PivotPhaseDiagramSelection: Hashable, Identifiable {
    case none, pivotIn, leaving, retraceConfirmed, divergence
    case edgeForm, edgeBreak, edgeHold, edgeDiverge, edgeFake, edgeReverse

    var id: Self { self }

    /// 后端 `PivotPhase.phase` 字符串 → 图上对应的节点。
    static func node(for phase: String) -> PivotPhaseDiagramSelection {
        switch phase {
        case "pivot_forming", "pivot_oscillating": return .pivotIn
        case "leaving": return .leaving
        case "retrace_confirmed": return .retraceConfirmed
        case "divergence_turn": return .divergence
        default: return .none
        }
    }
}

struct PhaseDiagramCopy {
    let title: String
    let body: String

    /// 各方块/边的通用规则讲解——跟具体某支股票无关，点开对应的 `PhaseRuleSheet`
    /// 时用这份文案。「这支股票现在的具体结论」另见 `PivotPhaseDiagram.detailPanel`
    /// 用的 `phase.reason`，两者不共用同一套文案。
    /// 流程图上每个框（状态）与每条线（动作）的名字——图上的框、线标签、讲解弹窗标题、
    /// 以及外面「阶段流程图 · 当前在「X」」都读这里，保证处处同名。叫法贴合缠论原文：
    /// 中枢形成 / 震荡、离开中枢、背驰；原文的「回试 / 回抽」用大白话「回落 / 反弹」，
    /// ZG / ZD 写成「中枢上沿 / 下沿」（与后端 app/services/chan/pivot_phase.py 同一套词表）。
    static func name(of selection: PivotPhaseDiagramSelection) -> String {
        switch selection {
        case .none: return L("无中枢")
        case .pivotIn: return L("中枢震荡")
        case .leaving: return L("离开中枢")
        case .retraceConfirmed: return L("确认买卖点")
        case .divergence: return L("背驰 / 转折")
        case .edgeForm: return L("形成中枢")
        case .edgeBreak: return L("突破")
        case .edgeHold: return L("回落 / 反弹")
        case .edgeDiverge: return L("背驰")
        case .edgeFake: return L("回到中枢")
        case .edgeReverse: return L("反向突破")
        }
    }

    /// 各方块/边的通用规则讲解——跟具体某支股票无关，点开对应的 `PhaseRuleSheet`
    /// 时用这份文案。「这支股票现在的具体结论」另见详情页的「这意味着什么」。
    static func copy(for selection: PivotPhaseDiagramSelection) -> PhaseDiagramCopy {
        let n = name(of: selection)
        switch selection {
        case .none:
            return PhaseDiagramCopy(title: n,
                body: L("笔数不足 3 笔，或者当前还没有可用的中枢——这是兜底状态，不是判定结果，不产生买卖点。"))
        case .pivotIn:
            return PhaseDiagramCopy(title: n,
                body: L("三段走势重叠形成中枢之后，价格在中枢上沿与下沿之间反复（也叫中枢延伸），还没有一笔从中枢内出发、收在中枢外。这个阶段不产生买卖点。"))
        case .leaving:
            return PhaseDiagramCopy(title: n,
                body: L("一笔从中枢内出发，向上收在中枢上沿之上、或向下收在中枢下沿之下，就是离开中枢。这是第三类买卖点的候选，还要等之后的回落（向上离开时）或反弹（向下离开时）来确认。"))
        case .retraceConfirmed:
            return PhaseDiagramCopy(title: n,
                body: L("离开中枢后的回落 / 反弹没有回到中枢 → 三买 / 三卖；回到了中枢里、但没有穿过另一侧边沿 → 二买 / 二卖。强弱看中枢级别，以及回落 / 反弹离中枢边沿还有多远。"))
        case .divergence:
            return PhaseDiagramCopy(title: n,
                body: L("买卖点确认之后，同方向继续走出新高 / 新低，但价差、量能或时长比前一段更弱，就是背驰（向上叫顶背驰，向下叫底背驰），对应一卖或一买。"))
        case .edgeForm:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("连续三段走势的价格区间有重叠，重叠的部分就是中枢——后面所有判断都从它开始。"))
        case .edgeBreak:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("一笔从中枢内出发，收在中枢上沿之上或下沿之下，进入「离开中枢」。"))
        case .edgeHold:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("离开中枢之后第一段反向走势：向上离开后叫回落，向下离开后叫反弹。没有回到中枢（三类），或回到中枢但没有穿过另一侧边沿（二类），进入「确认买卖点」。"))
        case .edgeDiverge:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("买卖点确认之后，同方向继续前进的笔，力度（价差 / 量能 / 时长）比前一个同向段更弱，进入「背驰 / 转折」。"))
        case .edgeFake:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("回落 / 反弹直接穿过了中枢另一侧边沿，重新回到中枢里——这次离开不算数，退回「中枢震荡」重新判断。"))
        case .edgeReverse:
            return PhaseDiagramCopy(title: L("动作：%@", n),
                body: L("「确认买卖点」或「背驰 / 转折」之后，出现一次方向相反的突破并完成回落 / 反弹确认——整体重新判定，结论以新的为准。"))
        }
    }
}

/// 结构位置：全部可能结果的全局判定图。上面的卡片固定展示这一次的真实判定
/// 依据（`phase.phaseLabel`/`phase.reason`），不随点击变化；点任意方块/线
/// 上滑弹出一个独立页面看它的通用规则——两者职责不同，互不打扰。
struct PivotPhaseDiagram: View {
    let phase: PivotPhase
    /// 卡片实际可用宽度，由 `ResultDetailView` 在页面顶层测量一次后逐层传下来
    /// （见 `ResultDetailView.pageContentWidth` 的说明）。传 nil 时退回 `designWidth`。
    var availableWidth: CGFloat?
    /// false = 只画流程图：标题、原因、下一步已经在结论卡与「这意味着什么」里，展开流程图时
    /// 不再重复一遍（详情页折叠区用）。
    var showsDetail = true
    /// 点了哪个方块/边，非 nil 时弹出对应的规则讲解页。跟上面卡片的内容
    /// 完全独立，卡片永远只展示 `phase` 算出来的当前状态。
    @State private var sheetSelection: PivotPhaseDiagramSelection?

    // 设计坐标系：所有节点/边坐标都按这个基准写死，绘制时统一乘 scale。
    private let designWidth: CGFloat = 394
    private let designHeight: CGFloat = 460

    private struct NodeSpec {
        let key: PivotPhaseDiagramSelection
        let rect: CGRect
        let title: String
        let dashed: Bool
        let hasDeliverable: Bool
        let isCurrent: Bool
    }

    private struct Edge {
        let key: PivotPhaseDiagramSelection
        let from: CGPoint
        let to: CGPoint
        let control1: CGPoint?
        let control2: CGPoint?
        let label: String
        /// 标签左边缘中点：标签贴在线（曲线取最外侧）右边，不随文字长短漂移。
        let labelPos: CGPoint
        let color: Color
    }

    private var currentNode: PivotPhaseDiagramSelection { .node(for: phase.phase) }

    private var nodeSpecs: [NodeSpec] {
        [
            NodeSpec(key: .none, rect: CGRect(x: 145, y: 14, width: 104, height: 26),
                     title: PhaseDiagramCopy.name(of: .none), dashed: true, hasDeliverable: false, isCurrent: currentNode == .none),
            NodeSpec(key: .pivotIn, rect: CGRect(x: 112, y: 70, width: 170, height: 46),
                     title: PhaseDiagramCopy.name(of: .pivotIn), dashed: false, hasDeliverable: false, isCurrent: currentNode == .pivotIn),
            NodeSpec(key: .leaving, rect: CGRect(x: 112, y: 174, width: 170, height: 46),
                     title: PhaseDiagramCopy.name(of: .leaving), dashed: false, hasDeliverable: true, isCurrent: currentNode == .leaving),
            NodeSpec(key: .retraceConfirmed, rect: CGRect(x: 100, y: 278, width: 194, height: 54),
                     title: PhaseDiagramCopy.name(of: .retraceConfirmed), dashed: false, hasDeliverable: true, isCurrent: currentNode == .retraceConfirmed),
            NodeSpec(key: .divergence, rect: CGRect(x: 112, y: 386, width: 170, height: 46),
                     title: PhaseDiagramCopy.name(of: .divergence), dashed: false, hasDeliverable: true, isCurrent: currentNode == .divergence),
        ]
    }

    private let edges: [Edge] = [
        Edge(key: .edgeForm, from: CGPoint(x: 197, y: 40), to: CGPoint(x: 197, y: 70),
             control1: nil, control2: nil, label: PhaseDiagramCopy.name(of: .edgeForm), labelPos: CGPoint(x: 199, y: 55), color: Theme.textSecondary),
        Edge(key: .edgeBreak, from: CGPoint(x: 197, y: 116), to: CGPoint(x: 197, y: 174),
             control1: nil, control2: nil, label: PhaseDiagramCopy.name(of: .edgeBreak), labelPos: CGPoint(x: 199, y: 145), color: Theme.textSecondary),
        Edge(key: .edgeHold, from: CGPoint(x: 197, y: 220), to: CGPoint(x: 197, y: 278),
             control1: nil, control2: nil, label: PhaseDiagramCopy.name(of: .edgeHold), labelPos: CGPoint(x: 199, y: 249), color: Theme.textSecondary),
        Edge(key: .edgeDiverge, from: CGPoint(x: 197, y: 332), to: CGPoint(x: 197, y: 386),
             control1: nil, control2: nil, label: PhaseDiagramCopy.name(of: .edgeDiverge), labelPos: CGPoint(x: 199, y: 359), color: Theme.textSecondary),
        Edge(key: .edgeFake, from: CGPoint(x: 282, y: 198), to: CGPoint(x: 284, y: 94),
             control1: CGPoint(x: 340, y: 198), control2: CGPoint(x: 340, y: 94),
             label: PhaseDiagramCopy.name(of: .edgeFake), labelPos: CGPoint(x: 328, y: 146), color: Theme.segment),
        Edge(key: .edgeReverse, from: CGPoint(x: 282, y: 410), to: CGPoint(x: 284, y: 198),
             control1: CGPoint(x: 352, y: 410), control2: CGPoint(x: 352, y: 198),
             label: PhaseDiagramCopy.name(of: .edgeReverse), labelPos: CGPoint(x: 337, y: 304), color: Theme.stroke),
    ]

    var body: some View {
        detailPanel
            .sheet(item: $sheetSelection) { selection in
                PhaseRuleSheet(selection: selection)
                    .presentationDetents([.fraction(0.4), .medium])
                    .presentationDragIndicator(.visible)
                    .preferredColorScheme(.dark)
            }
    }

    @ViewBuilder
    private var diagramCanvas: some View {
        let width = availableWidth ?? designWidth
        let scale = width / designWidth
        ZStack(alignment: .topLeading) {
            Canvas { ctx, _ in drawEdges(ctx, scale: scale) }
            // 线本身也要能点，不能只靠标签那一小块文字——Canvas 画的线没有
            // 手势，之前点线基本没反应，只有精准点中标签才有用。放在节点
            // 之前，避免短竖线贴着节点边界时抢了节点的点击。
            ForEach(edges, id: \.key) { edge in
                edgeHitArea(edge, scale: scale)
            }
            ForEach(nodeSpecs, id: \.key) { spec in
                nodeView(spec, scale: scale)
            }
            ForEach(edges, id: \.key) { edge in
                edgeLabel(edge, scale: scale)
            }
        }
        .frame(width: width, height: designHeight * scale)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(L("结构位置全局判定图"))
    }

    // MARK: - 节点

    private func nodeView(_ spec: NodeSpec, scale: CGFloat) -> some View {
        // 5 个节点只按「是不是当前状态」决定高亮，不再有「点击后选中」这个中间态——
        // 点节点是去弹讲解页，不是把这个节点变成焦点，视觉上不需要区分两者。
        return Button {
            sheetSelection = spec.key
        } label: {
            RoundedRectangle(cornerRadius: 10 * scale)
                .fill(Theme.surfaceAlt)
                .overlay(
                    RoundedRectangle(cornerRadius: 10 * scale)
                        // 非当前节点不用 Theme.border：它和节点底色 surfaceAlt 几乎同色，边框看不出来。
                        .strokeBorder(spec.isCurrent ? Theme.phaseColor(phase: phase.phase, direction: phase.direction) : Theme.textSecondary.opacity(0.6),
                                      style: StrokeStyle(lineWidth: (spec.isCurrent ? 2.2 : 1.5) * scale,
                                                          dash: spec.dashed ? [4 * scale, 3 * scale] : []))
                )
                .overlay {
                    Text(spec.title)
                        .font(.system(size: (spec.key == .none ? 11 : 13) * scale, weight: .semibold))
                        .foregroundStyle(spec.key == .none ? Theme.textSecondary : Theme.textPrimary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .padding(.horizontal, 4 * scale)
                }
                .overlay(alignment: .topTrailing) {
                    if spec.isCurrent {
                        // 只标「当前」，不塞具体结论——具体结论（如「确认三买」）已经在
                        // 上面固定的卡片里完整展示，节点这个小徽标空间放不下长文案。
                        Text(L("当前"))
                            .font(.system(size: 9 * scale, weight: .bold))
                            .foregroundStyle(Theme.background)
                            .padding(.horizontal, 6 * scale).padding(.vertical, 2 * scale)
                            .background(Theme.currentBadge, in: Capsule())
                            .padding(4 * scale)
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    if spec.key != .none {
                        Group {
                            if spec.hasDeliverable {
                                Circle().fill(Theme.accent)
                            } else {
                                Circle().strokeBorder(Theme.textSecondary, lineWidth: 1)
                            }
                        }
                        .frame(width: 7 * scale, height: 7 * scale)
                        .padding(6 * scale)
                    }
                }
        }
        .buttonStyle(.plain)
        .frame(width: spec.rect.width * scale, height: spec.rect.height * scale)
        .position(x: spec.rect.midX * scale, y: spec.rect.midY * scale)
        .accessibilityLabel(spec.title)
    }

    // MARK: - 边（可点的标签 + 可点的线本身 + Canvas 画的视觉线/曲线）

    /// 沿整条线/曲线给一条加宽的透明可点区域，而不是只有 labelPos 那一小块文字——
    /// 视觉线是 Canvas 画的，Canvas 内容本身没有手势，之前只能精准点中标签才有反应。
    private struct EdgePath: Shape {
        let from: CGPoint
        let to: CGPoint
        let control1: CGPoint?
        let control2: CGPoint?

        func path(in rect: CGRect) -> Path {
            var path = Path()
            path.move(to: from)
            if let c1 = control1, let c2 = control2 {
                path.addCurve(to: to, control1: c1, control2: c2)
            } else {
                path.addLine(to: to)
            }
            return path
        }
    }

    private func edgeHitArea(_ edge: Edge, scale: CGFloat) -> some View {
        let shape = EdgePath(
            from: CGPoint(x: edge.from.x * scale, y: edge.from.y * scale),
            to: CGPoint(x: edge.to.x * scale, y: edge.to.y * scale),
            control1: edge.control1.map { CGPoint(x: $0.x * scale, y: $0.y * scale) },
            control2: edge.control2.map { CGPoint(x: $0.x * scale, y: $0.y * scale) })
        let hitStyle = StrokeStyle(lineWidth: 26 * scale, lineCap: .round)
        // `strokedPath` 是 Path 的方法，不是 Shape 的——先拿 EdgePath 的 Path 实例
        // 再加粗轮廓，才能喂给 contentShape。
        let hitPath = shape.path(in: .zero).strokedPath(hitStyle)
        return shape
            .stroke(Color.clear, style: hitStyle)
            .contentShape(hitPath)
            .onTapGesture { sheetSelection = edge.key }
            // 只是给 edgeLabel 加大点击范围，语义上是同一个东西——VoiceOver 交给
            // 下面那个有文字的 edgeLabel 播报就够了，这层不重复念一遍。
            .accessibilityHidden(true)
    }

    private func edgeLabel(_ edge: Edge, scale: CGFloat) -> some View {
        Button {
            sheetSelection = edge.key
        } label: {
            Text(edge.label)
                .font(.system(size: 10 * scale, weight: .regular))
                .foregroundStyle(Theme.textSecondary)
                .padding(.horizontal, 5 * scale).padding(.vertical, 2 * scale)
                .background(Color.clear, in: Capsule())
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .fixedSize()
        // 零尺寸锚点 + leading 对齐的 overlay：让标签左边缘落在 labelPos，而不是中心。
        .frame(width: 0, height: 0, alignment: .leading)
        .position(x: edge.labelPos.x * scale, y: edge.labelPos.y * scale)
    }

    private func drawEdges(_ ctx: GraphicsContext, scale: CGFloat) {
        func sp(_ pt: CGPoint) -> CGPoint { CGPoint(x: pt.x * scale, y: pt.y * scale) }
        for edge in edges {
            let isCurved = edge.control1 != nil
            var path = Path()
            path.move(to: sp(edge.from))
            let endAngle: CGFloat
            if let c1 = edge.control1, let c2 = edge.control2 {
                path.addCurve(to: sp(edge.to), control1: sp(c1), control2: sp(c2))
                endAngle = atan2(edge.to.y - c2.y, edge.to.x - c2.x)
            } else {
                path.addLine(to: sp(edge.to))
                endAngle = atan2(edge.to.y - edge.from.y, edge.to.x - edge.from.x)
            }
            let color = isCurved ? edge.color : Theme.textSecondary
            let opacity: Double = isCurved ? 0.55 : 0.7
            let width = (isCurved ? 1.3 : 1.4) * scale
            ctx.stroke(path, with: .color(color.opacity(opacity)),
                       style: StrokeStyle(lineWidth: width, dash: isCurved ? [4 * scale, 3 * scale] : []))
            ctx.fill(arrowhead(at: sp(edge.to), angle: endAngle, size: 6 * scale),
                     with: .color(color.opacity(opacity)))
        }
    }

    private func arrowhead(at point: CGPoint, angle: CGFloat, size: CGFloat) -> Path {
        var path = Path()
        let p1 = CGPoint(x: point.x - size * cos(angle - .pi / 6), y: point.y - size * sin(angle - .pi / 6))
        let p2 = CGPoint(x: point.x - size * cos(angle + .pi / 6), y: point.y - size * sin(angle + .pi / 6))
        path.move(to: point)
        path.addLine(to: p1)
        path.addLine(to: p2)
        path.closeSubpath()
        return path
    }

    // MARK: - 详情面板

    /// 固定展示这一次算出来的当前状态，不受下面图上点了哪个方块/边影响——
    /// 那些点击只弹讲解页（见 `PhaseRuleSheet`），跟这张卡片各管各的。
    private var detailPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            if showsDetail {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text(phase.phaseLabel)
                        .font(AnalysisType.title)
                        .foregroundStyle(Theme.phaseColor(phase: phase.phase, direction: phase.direction))
                    Text(L("当前"))
                        .font(.caption2.bold())
                        .foregroundStyle(Theme.background)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Theme.currentBadge, in: Capsule())
                    Spacer(minLength: 0)
                    if !phase.confirmed {
                        Label(L("未确认"), systemImage: "circle.dashed")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                Text(HeadlineHighlighter.highlight(phase.reason))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lineSpacing(AnalysisType.bodyLineSpacing)
                Text(L("参考中枢（%@）：下沿 %@ — 上沿 %@",
                       phase.pivot.level == .segment ? L("线段级") : L("笔级"),
                       String(format: "%.2f", phase.pivot.zd),
                       String(format: "%.2f", phase.pivot.zg)))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
                if let next = phase.checklist.first(where: { $0.state == .pending }) {
                    Text(L("下一步观察：%@", next.label))
                        .font(.caption)
                        .foregroundStyle(Theme.accent)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            }

            diagramCanvas

            Text(L("● 有买卖点信号　○ 没有信号 · 点框或点线看规则"))
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// 点判定图上任意方块/线，上滑弹出的规则讲解页——跟上面固定的状态卡片是两件事：
/// 卡片说「这支股票现在在哪」，这个页面说「这个方块/边的规则是什么」，互不影响。
private struct PhaseRuleSheet: View {
    let selection: PivotPhaseDiagramSelection
    @Environment(\.dismiss) private var dismiss

    private var copy: PhaseDiagramCopy { PhaseDiagramCopy.copy(for: selection) }

    var body: some View {
        NavigationStack {
            ScrollView {
                Text(copy.body)
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textPrimary)
                    .lineSpacing(AnalysisType.bodyLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(20)
            }
            .background(Theme.background)
            .navigationTitle(copy.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
    }
}
