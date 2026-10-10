import SwiftUI

/// 图例兼作图层开关，竖屏、全屏与分享长图共用同一份显示状态。
///
/// 紧贴图表上方：紧凑小标签、放不下自动换行；关掉的图层变淡。
struct ChartLegend: View {
    @ObservedObject var vm: ChanViewModel
    var isStatic = false
    /// 可用宽度上限。
    var maxWidth: CGFloat = .infinity
    /// 紧凑模式（详情页竖屏）：只摆笔 / 中枢 / 买卖点三个常用开关，分型 / 线段 / 背驰和
    /// 「虚线=未确认」收进「更多图层」菜单，图例压成一行。全屏图与分享长图用完整图例。
    var compact = false
    /// 有分析结果时才能放「对比」下拉框（要知道威科夫 / SMC 有没有数据）；分享长图（isStatic）里不放。
    var analysis: ChanAnalysis? = nil

    var body: some View {
        if compact && !isStatic {
            compactLegend
        } else {
            fullLegend
        }
    }

    private var compactLegend: some View {
        HStack(spacing: 6) {
            item(Theme.stroke, "笔", isOn: $vm.showStrokes)
            item(Theme.pivotFill, "中枢", isOn: $vm.showPivots)
            item(Theme.up, "买卖点", isOn: $vm.showSignals, secondaryColor: Theme.down)
            Menu {
                Toggle(L("分型"), isOn: $vm.showFractals)
                Toggle(L("线段"), isOn: $vm.showSegments)
                Toggle(L("背驰"), isOn: $vm.showDivergences)
                Section(L("虚线=未确认")) {}
            } label: {
                HStack(spacing: 3) {
                    Text(L("更多图层"))
                    if moreOnCount > 0 { Text("\(moreOnCount)").foregroundStyle(Theme.accent) }
                    Image(systemName: "chevron.down").font(.system(size: 7, weight: .bold))
                }
                .font(.system(size: 9.5, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
                .padding(.horizontal, 6).padding(.vertical, 2.5)
                .background(Theme.surfaceAlt.opacity(0.72), in: Capsule())
            }
            Spacer(minLength: 0)
            // 图右上方（图外）：拿别的看盘方法和缠论对比
            techniqueMenu
        }
        .frame(maxWidth: maxWidth, alignment: .leading)
    }

    /// 可选的对比技术：威科夫 / SMC，要这张图真有数据才列出来。
    private var availableTechniques: [ChartIndicator] {
        guard let analysis else { return [] }
        return ChartIndicator.comparisons.filter { t in
            switch t {
            case .wyckoff: return analysis.wyckoff != nil
            case .smc: return analysis.smc != nil
            default: return false
            }
        }
    }

    /// 「对比」下拉框：选一个技术就把缠论图层收起来、只画它；选「缠论」回到默认。以后新增的对比技术加进
    /// `ChartIndicator.comparisons` 即可。选了 SMC 时多一个子菜单，勾选图上画哪几类。
    @ViewBuilder
    private var techniqueMenu: some View {
        if !isStatic, !availableTechniques.isEmpty {
            let current = vm.comparison
            Menu {
                Button { vm.setComparison(nil) } label: {
                    Label(L("缠论（默认）"), systemImage: current == nil ? "checkmark" : "scope")
                }
                ForEach(availableTechniques) { t in
                    Button { vm.setComparison(t) } label: {
                        if current == t { Label(t.title, systemImage: "checkmark") } else { Text(t.title) }
                    }
                }
                if current == .smc {
                    Divider()
                    Menu(L("SMC 显示内容")) {
                        Toggle(L("结构突破 / 转变"), isOn: $vm.smcLayers.structure)
                        Toggle(L("订单块"), isOn: $vm.smcLayers.orderBlocks)
                        Toggle(L("公允价值缺口"), isOn: $vm.smcLayers.fvg)
                        Toggle(L("强弱高低点"), isOn: $vm.smcLayers.strongWeak)
                        Toggle(L("溢价 / 折价区"), isOn: $vm.smcLayers.premiumDiscount)
                        Toggle(L("等高 / 等低点"), isOn: $vm.smcLayers.equalLevels)
                        Toggle(L("流动性扫荡"), isOn: $vm.smcLayers.sweeps)
                        Toggle(L("前周期高低点"), isOn: $vm.smcLayers.keyLevels)
                    }
                }
            } label: {
                HStack(spacing: 3) {
                    Text(current?.title ?? L("对比"))
                    Image(systemName: "chevron.down").font(.system(size: 7, weight: .bold))
                }
                .font(.system(size: 9.5, weight: current == nil ? .medium : .semibold))
                .foregroundStyle(current == nil ? Theme.textSecondary : Theme.accent)
                .padding(.horizontal, 8).padding(.vertical, 2.5)
                .background(current == nil ? Theme.surfaceAlt.opacity(0.72) : Theme.accent.opacity(0.16), in: Capsule())
            }
            .accessibilityLabel(L("对比技术"))
        }
    }

    /// 「更多图层」里当前打开了几个，标在按钮上，免得用户忘了图上多画了什么。
    private var moreOnCount: Int {
        [vm.showFractals, vm.showSegments, vm.showDivergences].filter { $0 }.count
    }

    private var fullLegend: some View {
        WrapLayout(spacing: 4, lineSpacing: 3) {
                // 顶底分型沿用原先同一个图层开关；两个小圆点（顶/底色）与图上分型圆点一致。
                item(Theme.topFractal, "分型", isOn: $vm.showFractals,
                     secondaryColor: Theme.bottomFractal, dotted: true)
                item(Theme.stroke, "笔", isOn: $vm.showStrokes)
                item(Theme.segment, "线段", isOn: $vm.showSegments)
                item(Theme.pivotFill, "中枢", isOn: $vm.showPivots)
                item(Theme.up, "买卖点", isOn: $vm.showSignals, secondaryColor: Theme.down)
                item(Theme.divergence, "背驰", isOn: $vm.showDivergences)
                // 说明放进同一个换行流里，不单独占一行
                Text(L("虚线=未确认"))
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 2)
                techniqueMenu
        }
        .frame(maxWidth: maxWidth, alignment: .leading)
    }

    private func item(
        _ color: Color, _ title: String, isOn: Binding<Bool>, secondaryColor: Color? = nil,
        dotted: Bool = false
    ) -> some View {
        Toggle(isOn: isOn) {
            HStack(spacing: 3) {
                if dotted {
                    HStack(spacing: 1.5) {
                        Circle().fill(color).frame(width: 5, height: 5)
                        if let secondaryColor {
                            Circle().fill(secondaryColor).frame(width: 5, height: 5)
                        }
                    }
                } else {
                    VStack(spacing: 1.5) {
                        Capsule().fill(color).frame(width: 8, height: 2.5)
                        if let secondaryColor {
                            Capsule().fill(secondaryColor).frame(width: 8, height: 2.5)
                        }
                    }
                }
                Text(L(title)).font(.system(size: 9.5, weight: .medium))
            }
            .foregroundStyle(isOn.wrappedValue ? Theme.textPrimary : Theme.textSecondary)
            .opacity(isOn.wrappedValue ? 1 : 0.45)
            .padding(.horizontal, 5)
            .padding(.vertical, 2.5)
            .background(Theme.surfaceAlt.opacity(0.72), in: Capsule())
            .contentShape(Capsule())
        }
        .toggleStyle(ChartLayerToggleStyle())
        .allowsHitTesting(!isStatic)
    }
}

/// 简单的自动换行布局：一行放不下就折到下一行（图例在英文下更长）。
struct WrapLayout: Layout {
    var spacing: CGFloat = 4
    var lineSpacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let width = rows.map { $0.width }.max() ?? 0
        let height = rows.reduce(0) { $0 + $1.height } + lineSpacing * CGFloat(max(0, rows.count - 1))
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for idx in row.indices {
                let size = subviews[idx].sizeThatFits(.unspecified)
                subviews[idx].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2),
                                    proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private struct Row { var indices: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = [Row()]
        for (idx, sub) in subviews.enumerated() {
            let size = sub.sizeThatFits(.unspecified)
            let extra = rows[rows.count - 1].indices.isEmpty ? size.width : size.width + spacing
            if rows[rows.count - 1].width + extra > width, !rows[rows.count - 1].indices.isEmpty {
                rows.append(Row())
            }
            var row = rows[rows.count - 1]
            row.width += row.indices.isEmpty ? size.width : size.width + spacing
            row.height = max(row.height, size.height)
            row.indices.append(idx)
            rows[rows.count - 1] = row
        }
        return rows
    }
}
