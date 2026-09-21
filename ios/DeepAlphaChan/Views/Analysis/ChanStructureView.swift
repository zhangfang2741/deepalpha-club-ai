import SwiftUI

/// 分段控件的「结构」段：把缠论结构画成「框（隶属）+ 带（中枢）+ 点（买卖点）」，
/// 主图保持干净，点任意元素 → 从底部弹出详情（是什么 / 为什么 / 概念），中枢类
/// 元素的弹层里还能继续下钻看次级别（多周期）。
///
/// 视觉语言（对应缠论真实关系，见 ChanStructureInfo）：
/// - **框**：隶属构成 走势 ⊃ 线段 ⊃ 笔（真·大套小），用嵌套边框；
/// - **带**：中枢——由笔 / 线段重叠围出的 ZG–ZD 区间，用上下虚线的横带；多个中枢
///   =多条带，条数与排布本身就是盘整 / 趋势的定义；
/// - **点**：买卖点——挂在中枢带上的一个点（候选 / 确认）。
///
/// 所有当前状态由 ChanStructureInfo 从 `ChanAnalysis` 推导，不写死场景。
struct ChanStructureView: View {
    let analysis: ChanAnalysis

    @State private var selected: ChanRef?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            legend
            trendFrame
        }
        .sheet(item: $selected) { ref in
            StructureSheet(ref: ref, analysis: analysis)
                .presentationDetents([.medium, .large])
                .preferredColorScheme(.dark)
        }
    }

    private var legend: some View {
        Text(L("框=隶属 · 带=中枢 · 点=买卖点 · 虚线=未确认 · 点任意元素看详情"))
            .font(.system(size: 10))
            .foregroundColor(Theme.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - 走势框（隶属最外层）

    private var trendFrame: some View {
        let tColor = ChanStructureInfo.trendColor(analysis)
        return VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 6) {
                nameButton(L("大级别"), L("走势"), ref: .trend)
                Spacer(minLength: 6)
                divergenceChip
            }
            regimePills
            PivotBands(analysis: analysis, selected: $selected)
            invalidationRow
            Text(pivotCaption)
                .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            segmentFrame
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tColor.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 15))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(tColor.opacity(0.35), lineWidth: 1.5))
    }

    private var divergenceChip: some View {
        Button { selected = .divergence } label: {
            HStack(spacing: 4) {
                Image(systemName: "waveform.path.ecg").font(.system(size: 9))
                Text(divergenceLabel).font(.system(size: 10))
            }
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Theme.segment.opacity(0.12))
            .foregroundColor(Theme.segment)
            .overlay(Capsule().stroke(Theme.segment.opacity(0.4), lineWidth: 1))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private var divergenceLabel: String {
        switch ChanStructureInfo.divergenceKey(analysis) {
        case "top": return L("顶背驰 已现")
        case "bottom": return L("底背驰 已现")
        default: return L("背驰 未现")
        }
    }

    private var regimePills: some View {
        let cur = ChanStructureInfo.walkKey(analysis)
        return HStack(spacing: 5) {
            classifyPill(L("盘整"), active: cur == "consolidation", color: Theme.segment, ref: .regime("range"))
            classifyPill(L("上涨趋势"), active: cur == "up_trend", color: Theme.up, ref: .regime("up"))
            classifyPill(L("下跌趋势"), active: cur == "down_trend", color: Theme.down, ref: .regime("down"))
        }
    }

    private var invalidationRow: some View {
        Group {
            if let inv = ChanStructureInfo.invalidation(analysis) {
                Button { selected = .signal } label: {
                    HStack(spacing: 8) {
                        Text(L("⚑ 失效价 %@", ChanStructureInfo.fmt(inv.price)))
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(Theme.up)
                        Text(inv.isBuy ? L("跌回中枢即废 · 点看详情") : L("升回中枢即废 · 点看详情"))
                            .font(.system(size: 10.5)).foregroundColor(Theme.textSecondary)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.up.opacity(0.07))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var pivotCaption: String {
        let n = analysis.strokePivots.count
        if n >= 2 {
            let word = ChanStructureInfo.walkKey(analysis) == "up_trend" ? L("依次抬高") : L("依次降低")
            return L("%1$lld 个中枢%2$@ = 趋势（一条带=盘整）；中枢由下面的笔 / 线段重叠而成", n, word)
        }
        return L("中枢由下面的笔 / 线段重叠而成")
    }

    // MARK: - 线段框 ⊃ 笔框

    private var segmentFrame: some View {
        let segUp = analysis.segments.last?.direction == .up
        return VStack(alignment: .leading, spacing: 8) {
            nameButton(L("中期"), L("线段"), ref: .segment)
            HStack(spacing: 5) {
                classifyPill(L("向上"), active: segUp, color: Theme.segment, ref: .segDir(true))
                classifyPill(L("向下"), active: !segUp, color: Theme.segment, ref: .segDir(false))
                if !(analysis.segments.last?.confirmed ?? true) {
                    Text(L("· 未结束")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                }
            }
            strokeFrame
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(RoundedRectangle(cornerRadius: 11).stroke(Theme.segment.opacity(0.35), lineWidth: 1.5))
    }

    private var strokeFrame: some View {
        let forming = !(analysis.strokes.last?.confirmed ?? true)
        return VStack(alignment: .leading, spacing: 7) {
            nameButton(L("近期"), L("笔"), ref: .stroke, titleColor: Theme.stroke)
            HStack(spacing: 4) {
                stageChip(L("形成中"), status: forming ? .current : .done, ref: .strokeState(true), color: Theme.stroke)
                Text("→").foregroundColor(Theme.textSecondary)
                stageChip(L("已确认"), status: forming ? .future : .current, ref: .strokeState(false), color: Theme.stroke)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Theme.stroke.opacity(0.35), lineWidth: 1.5))
    }

    // MARK: - 复用小组件

    /// 结构名字按钮（点看该结构是什么）。
    private func nameButton(_ eyebrow: String, _ title: String, ref: ChanRef, titleColor: Color = Theme.textPrimary) -> some View {
        Button { selected = ref } label: {
            HStack(spacing: 6) {
                Text(eyebrow).font(.system(size: 9)).tracking(1.2).foregroundColor(Theme.textSecondary)
                Text(title).font(.system(size: 13, weight: .bold)).foregroundColor(titleColor)
                Image(systemName: "info.circle").font(.system(size: 9)).foregroundColor(Theme.textSecondary)
            }
        }
        .buttonStyle(.plain)
    }

    /// 分类色块（走势两分 / 线段方向）：active=实心亮色，否则虚线描边。
    private func classifyPill(_ text: String, active: Bool, color: Color, ref: ChanRef) -> some View {
        Button { selected = ref } label: {
            Text(text)
                .font(.system(size: 10.5, weight: active ? .bold : .regular))
                .padding(.horizontal, 8).padding(.vertical, 2.5)
                .background(active ? color : Color.clear)
                .foregroundColor(active ? Theme.background : Theme.textSecondary)
                .overlay(Capsule().stroke(active ? Color.clear : Theme.border,
                                          style: StrokeStyle(lineWidth: 1, dash: active ? [] : [3, 2])))
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    /// 生命周期步骤色块：done=暗填+✓，current=亮填+光晕，future=虚线描边。
    private func stageChip(_ text: String, status: ChipStatus, ref: ChanRef, color: Color) -> some View {
        stageChipView(text: text, status: status, color: color) { selected = ref }
    }
}

/// 只画上下两条边（中枢带的 ZG / ZD 虚线）。
struct TopBottomDashed: Shape {
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        p.move(to: CGPoint(x: rect.minX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        return p
    }
}

/// 生命周期步骤色块（独立成函数视图，PivotBands 也复用）。
func stageChipView(text: String, status: ChipStatus, color: Color, action: @escaping () -> Void) -> some View {
    Button(action: action) {
        HStack(spacing: 3) {
            Text(text).font(.system(size: 10, weight: status == .current ? .bold : .regular))
            if status == .done {
                Image(systemName: "checkmark").font(.system(size: 8, weight: .bold))
            }
        }
        .padding(.horizontal, 6).padding(.vertical, 2)
        .foregroundColor(status == .current ? Theme.background : (status == .done ? color : Theme.textSecondary))
        .background(status == .current ? color : (status == .done ? color.opacity(0.14) : Color.clear))
        .overlay(
            Capsule().stroke(
                status == .future ? Theme.border : (status == .done ? color.opacity(0.4) : Color.clear),
                style: StrokeStyle(lineWidth: 1, dash: status == .future ? [3, 2] : []))
        )
        .clipShape(Capsule())
    }
    .buttonStyle(.plain)
}

// MARK: - 中枢序列（带）

/// 多个中枢 = 多条带：更早的中枢压缩成暗带，最新中枢展开（生命周期 stepper + 买卖点点）。
private struct PivotBands: View {
    let analysis: ChanAnalysis
    @Binding var selected: ChanRef?

    var body: some View {
        let pivots = analysis.strokePivots
        return VStack(alignment: .leading, spacing: 4) {
            if pivots.isEmpty {
                emptyBand
            } else {
                ForEach(pivots.indices, id: \.self) { idx in
                    if idx == pivots.count - 1 {
                        activeBand(pivots[idx], index: idx)
                    } else {
                        compactBand(pivots[idx], index: idx)
                        stepConnector
                    }
                }
            }
        }
    }

    private var emptyBand: some View {
        Button { selected = .pivot(0) } label: {
            HStack {
                Text(L("尚未形成中枢 · 单边推进"))
                    .font(.system(size: 11.5, weight: .semibold)).foregroundColor(Theme.textSecondary)
                Spacer()
                Image(systemName: "info.circle").font(.system(size: 9)).foregroundColor(Theme.textSecondary)
            }
            .padding(.vertical, 6).padding(.horizontal, 10)
            .frame(maxWidth: .infinity)
            .overlay(bandBorders(opacity: 0.35))
        }
        .buttonStyle(.plain)
    }

    private var stepConnector: some View {
        let word = ChanStructureInfo.walkKey(analysis) == "up_trend" ? L("↑ 依次抬高") : L("↓ 依次降低")
        return Text(word)
            .font(.system(size: 9.5)).foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity, alignment: .center)
    }

    private func compactBand(_ p: Pivot, index: Int) -> some View {
        Button { selected = .pivot(index) } label: {
            HStack(spacing: 6) {
                Text(L("中枢%1$@ %2$@", mark(index), "\(ChanStructureInfo.fmt(p.zd))–\(ChanStructureInfo.fmt(p.zg))"))
                    .font(.system(size: 11.5, weight: .semibold)).foregroundColor(Theme.pivotFill.opacity(0.75))
                Text(L("已完成")).font(.system(size: 9.5)).foregroundColor(Theme.textSecondary)
                Spacer(minLength: 0)
                Image(systemName: "info.circle").font(.system(size: 8)).foregroundColor(Theme.textSecondary)
            }
            .padding(.vertical, 5).padding(.horizontal, 10)
            .frame(maxWidth: .infinity)
            .background(Theme.pivotFill.opacity(0.05))
            .overlay(bandBorders(opacity: 0.3))
        }
        .buttonStyle(.plain)
    }

    private func activeBand(_ p: Pivot, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Button { selected = .pivot(index) } label: {
                    HStack(spacing: 6) {
                        Text(L("中枢%1$@ %2$@", mark(index), "\(ChanStructureInfo.fmt(p.zd))–\(ChanStructureInfo.fmt(p.zg))"))
                            .font(.system(size: 12.5, weight: .bold)).foregroundColor(Theme.pivotFill)
                        Text(L("当前")).font(.system(size: 9.5)).foregroundColor(Theme.textSecondary)
                        Image(systemName: "info.circle").font(.system(size: 8)).foregroundColor(Theme.textSecondary)
                    }
                }
                .buttonStyle(.plain)
                Spacer(minLength: 4)
                signalPoint
            }
            lifecycleStepper
        }
        .padding(.vertical, 8).padding(.horizontal, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.pivotFill.opacity(0.08))
        .overlay(bandBorders(opacity: 1.0))
    }

    private var lifecycleStepper: some View {
        HStack(spacing: 3) {
            stageChipView(text: L("形成"), status: ChanStructureInfo.stageStatus(analysis, "form"), color: Theme.pivotFill) { selected = .stage("form") }
            Text("→").font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            stageChipView(text: L("震荡"), status: ChanStructureInfo.stageStatus(analysis, "osc"), color: Theme.pivotFill) { selected = .stage("osc") }
            Text("→").font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            stageChipView(text: L("离开"), status: ChanStructureInfo.stageStatus(analysis, "leave"), color: Theme.pivotFill) { selected = .stage("leave") }
            Text("→").font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            stageChipView(text: L("回抽"), status: ChanStructureInfo.stageStatus(analysis, "pull"), color: Theme.pivotFill) { selected = .stage("pull") }
        }
    }

    private var signalPoint: some View {
        Group {
            if let s = ChanStructureInfo.latestSignal(analysis) {
                Button { selected = .signal } label: {
                    HStack(spacing: 4) {
                        Circle().fill(s.isBuy ? Theme.up : Theme.down).frame(width: 7, height: 7)
                        Text(L("%1$@·%2$@", s.label, s.confirmed ? L("确认") : L("候选")))
                            .font(.system(size: 10.5))
                    }
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .foregroundColor(s.isBuy ? Theme.up : Theme.down)
                    .overlay(Capsule().stroke((s.isBuy ? Theme.up : Theme.down).opacity(0.4), lineWidth: 1))
                    .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func bandBorders(opacity: Double) -> some View {
        // 上下虚线 = ZG / ZD，中枢是「带」不是「框」
        TopBottomDashed().stroke(
            Theme.pivotFill.opacity(opacity),
            style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
    }

    private func mark(_ i: Int) -> String {
        guard analysis.strokePivots.count > 1 else { return "" }
        let marks = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
        return i < marks.count ? marks[i] : "\(i + 1)"
    }
}
