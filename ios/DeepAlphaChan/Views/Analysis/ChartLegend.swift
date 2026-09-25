import SwiftUI

/// 图例兼作图层开关，竖屏、全屏与分享长图共用同一份显示状态。
///
/// 紧贴图表上方：紧凑小标签、放不下自动换行；关掉的图层变淡。
struct ChartLegend: View {
    @ObservedObject var vm: ChanViewModel
    var isStatic = false
    /// 可用宽度上限。
    var maxWidth: CGFloat = .infinity

    var body: some View {
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
