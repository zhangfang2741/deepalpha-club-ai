import SwiftUI

/// 结构位置全局判定图里能点开详情的单元——5 个状态方块 + 6 条判定边。
///
/// 这是全部可能结果的地图，不是必然依次完成的进度条：`build_pivot_phase()`
/// 每次都拿完整笔历史重新判一遍，直接给出属于这 5 个方块之一的结果，不依赖
/// 上一次的结论（见 app/services/chan/pivot_phase.py 顶部 docstring）。
enum PivotPhaseDiagramSelection: Hashable {
    case none, pivotIn, leaving, retraceConfirmed, divergence
    case edgeForm, edgeBreak, edgeHold, edgeDiverge, edgeFake, edgeReverse

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

private struct DiagramWidthKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct PhaseDiagramCopy {
    let title: String
    let body: String

    /// 各方块/边的通用规则讲解——跟具体某支股票无关，点非当前状态时显示这个。
    /// 当前状态改显示 `phase.reason`（真实计算出来的判定依据），不用这份文案。
    static func copy(for selection: PivotPhaseDiagramSelection) -> PhaseDiagramCopy {
        switch selection {
        case .none:
            return PhaseDiagramCopy(
                title: L("无状态"),
                body: L("笔数不足 3 笔，或者当前没有可用的中枢——这是兜底状态，不是算出来的判定结果。交付物：无。"))
        case .pivotIn:
            return PhaseDiagramCopy(
                title: L("中枢内"),
                body: L("价格在中枢区间反复，最近的笔里还没有一笔「起点在中枢内、终点越过 ZG/ZD 边界」的笔。交付物：无买卖点信号，只更新中枢的 ZG/ZD 参考区间。"))
        case .leaving:
            return PhaseDiagramCopy(
                title: L("离开中枢"),
                body: L("出现一笔起点在中枢内、终点越过 ZG（向上）或 ZD（向下）的笔，正等它之后的回踩笔出现。交付物：候选三买/三卖，尚未确认。"))
        case .retraceConfirmed:
            return PhaseDiagramCopy(
                title: L("确认买卖点"),
                body: L("回踩笔收在越过原边界处 → 三买/三卖；收在区间内但没破对侧边界 → 二买/二卖。交付物：对应的买卖点信号，强度由中枢级别 + 回踩离边界的距离决定。"))
        case .divergence:
            return PhaseDiagramCopy(
                title: L("背驰 / 转折"),
                body: L("确认买卖点之后，后续同方向的笔里出现了背驰——创新高/新低，但价差、量能或时长比前一个同向段更弱。交付物：一买或一卖信号，强弱由这三项的比值决定。"))
        case .edgeForm:
            return PhaseDiagramCopy(
                title: L("条件：形成中枢"),
                body: L("最近的笔数达到 3 笔以上，且价格区间有重叠，构成一个中枢——这是后面所有判定的起点。"))
        case .edgeBreak:
            return PhaseDiagramCopy(
                title: L("条件：突破"),
                body: L("中枢形成之后，出现一笔起点在中枢内、终点越过 ZG 或 ZD 的笔，判定为「离开中枢」。"))
        case .edgeHold:
            return PhaseDiagramCopy(
                title: L("条件：回踩守住"),
                body: L("离开中枢之后的回踩笔，收在越过原边界处（三类）或区间内但未破对侧边界（二类），判定为「确认买卖点」。"))
        case .edgeDiverge:
            return PhaseDiagramCopy(
                title: L("条件：出现背驰"),
                body: L("确认买卖点之后，继续沿同一方向前进的笔里，力度（价差/量能/时长）比前一个同向段更弱，判定为「背驰」。"))
        case .edgeFake:
            return PhaseDiagramCopy(
                title: L("条件：假突破"),
                body: L("回踩笔直接穿破了对侧边界，整根笔又回到中枢区间内——这次突破作废，退回「中枢内」重新计算，不是终态。"))
        case .edgeReverse:
            return PhaseDiagramCopy(
                title: L("条件：反向突破"),
                body: L("「确认买卖点」或「背驰/转折」之后，后面出现一次方向相反、同样满足突破+回踩条件的新尝试——整体重新判定一次，结论会被新结果直接覆盖。"))
        }
    }
}

/// 结构位置：全部可能结果的全局判定图。点任意方块/线看它的通用规则；
/// 当前状态额外显示这一次的真实判定依据（`phase.reason`），一进来就知道
/// 「现在在哪、这一步为什么是这样」。
struct PivotPhaseDiagram: View {
    let phase: PivotPhase
    @State private var selected: PivotPhaseDiagramSelection

    init(phase: PivotPhase) {
        self.phase = phase
        _selected = State(initialValue: .node(for: phase.phase))
    }

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
        let labelPos: CGPoint
        let color: Color
    }

    private var currentNode: PivotPhaseDiagramSelection { .node(for: phase.phase) }

    private var nodeSpecs: [NodeSpec] {
        [
            NodeSpec(key: .none, rect: CGRect(x: 145, y: 14, width: 104, height: 26),
                     title: L("无状态"), dashed: true, hasDeliverable: false, isCurrent: currentNode == .none),
            NodeSpec(key: .pivotIn, rect: CGRect(x: 112, y: 70, width: 170, height: 46),
                     title: L("中枢内"), dashed: false, hasDeliverable: false, isCurrent: currentNode == .pivotIn),
            NodeSpec(key: .leaving, rect: CGRect(x: 112, y: 174, width: 170, height: 46),
                     title: L("离开中枢"), dashed: false, hasDeliverable: true, isCurrent: currentNode == .leaving),
            NodeSpec(key: .retraceConfirmed, rect: CGRect(x: 100, y: 278, width: 194, height: 54),
                     title: L("确认买卖点"), dashed: false, hasDeliverable: true, isCurrent: currentNode == .retraceConfirmed),
            NodeSpec(key: .divergence, rect: CGRect(x: 112, y: 386, width: 170, height: 46),
                     title: L("背驰 / 转折"), dashed: false, hasDeliverable: true, isCurrent: currentNode == .divergence),
        ]
    }

    private let edges: [Edge] = [
        Edge(key: .edgeForm, from: CGPoint(x: 197, y: 40), to: CGPoint(x: 197, y: 70),
             control1: nil, control2: nil, label: L("形成中枢"), labelPos: CGPoint(x: 253, y: 58), color: Theme.textSecondary),
        Edge(key: .edgeBreak, from: CGPoint(x: 197, y: 116), to: CGPoint(x: 197, y: 174),
             control1: nil, control2: nil, label: L("突破"), labelPos: CGPoint(x: 227, y: 148), color: Theme.textSecondary),
        Edge(key: .edgeHold, from: CGPoint(x: 197, y: 220), to: CGPoint(x: 197, y: 278),
             control1: nil, control2: nil, label: L("回踩守住"), labelPos: CGPoint(x: 253, y: 252), color: Theme.textSecondary),
        Edge(key: .edgeDiverge, from: CGPoint(x: 197, y: 332), to: CGPoint(x: 197, y: 386),
             control1: nil, control2: nil, label: L("背驰"), labelPos: CGPoint(x: 220, y: 362), color: Theme.textSecondary),
        Edge(key: .edgeFake, from: CGPoint(x: 282, y: 198), to: CGPoint(x: 284, y: 94),
             control1: CGPoint(x: 340, y: 198), control2: CGPoint(x: 340, y: 94),
             label: L("假突破"), labelPos: CGPoint(x: 349, y: 150), color: Theme.segment),
        Edge(key: .edgeReverse, from: CGPoint(x: 282, y: 410), to: CGPoint(x: 284, y: 198),
             control1: CGPoint(x: 352, y: 410), control2: CGPoint(x: 352, y: 198),
             label: L("反向突破"), labelPos: CGPoint(x: 356, y: 306), color: Theme.stroke),
    ]

    /// 卡片可用宽度，通过下面 `.background(GeometryReader …)` 的一次性测量写入——
    /// 不直接把图内容放进 GeometryReader：那样图会被拉伸/挤压成 GeometryReader
    /// 自己的尺寸提案，点击态引发的重新布局在部分机型上会让坐标和实际点击区域
    /// 对不上（表现为点一次之后所有节点/边都点不动）。测量与内容分离，图按测量
    /// 到的宽度用固定 frame 摆放，点击态变化不会反过来影响测量。
    @State private var measuredWidth: CGFloat?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // 先看文字说明（现在在哪、为什么），图放下面当作可交互的参考——
            // 一进来不用先看图才知道当前状态，点图上别的方块/线时上面这块跟着切换。
            detailPanel

            diagramCanvas
                .frame(maxWidth: .infinity)
                .background(
                    GeometryReader { geo in
                        Color.clear.preference(key: DiagramWidthKey.self, value: geo.size.width)
                    }
                )
                .onPreferenceChange(DiagramWidthKey.self) { width in
                    if width > 0 { measuredWidth = width }
                }

            Text(L("● 有买卖点信号　○ 没有信号 · 点框或点线看规则"))
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        // `selected` 用自定义 init 只在这个视图第一次被创建时按 phase 设初始值；
        // 之后只要外层还在同一个 tab（同一个 `.id(segment)`），切换股票/周期时
        // SwiftUI 会复用同一份视图身份，`selected` 不会自动跟着新的 phase 变化
        // ——不加这行会出现"当前"徽标指着新状态，高亮框却停在旧状态上的错位。
        // 用 reason 而不是 phase 判断变化：reason 带具体数值，同一个 phase 分类
        // 换了股票/中枢数值也一定不同，比只比较 phase 字符串更可靠。
        .onChange(of: phase.reason) { _, _ in
            selected = currentNode
        }
    }

    @ViewBuilder
    private var diagramCanvas: some View {
        let width = measuredWidth ?? designWidth
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
        let isSelected = selected == spec.key
        // 5 个节点统一用同一套高亮规则（只看 isCurrent/isSelected）——「确认买卖点」
        // 之前不论选没选都固定填中枢紫色，跟「当前」徽标各说各话，会让人误判当前
        // 在哪一步（比如真正当前是「中枢内」，视觉上最显眼的却是「确认买卖点」）。
        return Button {
            selected = spec.key
        } label: {
            RoundedRectangle(cornerRadius: 10 * scale)
                .fill(Theme.surfaceAlt)
                .overlay(
                    RoundedRectangle(cornerRadius: 10 * scale)
                        .strokeBorder(isSelected ? Theme.textPrimary.opacity(0.85) : Theme.border,
                                      style: StrokeStyle(lineWidth: (isSelected ? 2.2 : 1.2) * scale,
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
                        // 直接显示这次算出来的具体结论（如「确认三买」），不用固定的「当前」
                        // 两个字——自选列表的 Chip 用的就是同一个 phase.phaseLabel，两处
                        // 要看到一样的字，不然自选列表和判定图像是两套不同的结论。
                        Text(phase.phaseLabel)
                            .font(.system(size: 9 * scale, weight: .bold))
                            .foregroundStyle(Theme.background)
                            .lineLimit(1)
                            .minimumScaleFactor(0.6)
                            .frame(maxWidth: spec.rect.width * scale * 0.94)
                            .padding(.horizontal, 6 * scale).padding(.vertical, 2 * scale)
                            .background(Theme.pivotPhaseColor(phase.phase), in: Capsule())
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
            .onTapGesture { selected = edge.key }
            // 只是给 edgeLabel 加大点击范围，语义上是同一个东西——VoiceOver 交给
            // 下面那个有文字的 edgeLabel 播报就够了，这层不重复念一遍。
            .accessibilityHidden(true)
    }

    private func edgeLabel(_ edge: Edge, scale: CGFloat) -> some View {
        let isSelected = selected == edge.key
        return Button {
            selected = edge.key
        } label: {
            Text(edge.label)
                .font(.system(size: 10 * scale, weight: isSelected ? .bold : .regular))
                .foregroundStyle(isSelected ? edge.color : Theme.textSecondary)
                .padding(.horizontal, 5 * scale).padding(.vertical, 2 * scale)
                .background(isSelected ? Theme.surfaceAlt : Color.clear, in: Capsule())
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .position(x: edge.labelPos.x * scale, y: edge.labelPos.y * scale)
    }

    private func drawEdges(_ ctx: GraphicsContext, scale: CGFloat) {
        func sp(_ pt: CGPoint) -> CGPoint { CGPoint(x: pt.x * scale, y: pt.y * scale) }
        for edge in edges {
            let isSelected = selected == edge.key
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
            let opacity: Double = isSelected ? 1.0 : (isCurved ? 0.55 : 0.7)
            let width = (isSelected ? 2.4 : (isCurved ? 1.3 : 1.4)) * scale
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

    private var detailPanel: some View {
        let isCurrentSelection = selected == currentNode
        let copy = PhaseDiagramCopy.copy(for: selected)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                // 选中的正是当前状态时，标题换成这次算出来的具体结论（跟自选列表
                // Chip、图上节点徽标同一个 phase.phaseLabel）；选别的方块/线看
                // 通用规则时，还是用那个方块/边自己的名字（copy.title）。
                Text(isCurrentSelection ? phase.phaseLabel : copy.title)
                    .font(.subheadline.bold())
                    .foregroundStyle(Theme.textPrimary)
                if isCurrentSelection {
                    Text(L("当前"))
                        .font(.caption2.bold())
                        .foregroundStyle(Theme.background)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Theme.pivotPhaseColor(phase.phase), in: Capsule())
                }
                Spacer(minLength: 0)
                if isCurrentSelection && !phase.confirmed {
                    Label(L("未确认"), systemImage: "circle.dashed")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            Text(isCurrentSelection ? HeadlineHighlighter.highlight(phase.reason) : AttributedString(copy.body))
                .font(.footnote)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .lineSpacing(3)
            if isCurrentSelection {
                Text(L("参考中枢 %@ · 下沿 ZD %@ — 上沿 ZG %@",
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
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
    }
}
