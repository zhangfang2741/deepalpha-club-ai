import SwiftUI

/// 图例兼作图层开关，竖屏与全屏共用同一份显示状态。
struct ChartLegend: View {
    @ObservedObject var vm: ChanViewModel
    var isStatic = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if isStatic {
                // 分享长图直接展开，避免横向滚动容器截断图例。
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) { structureItems }
                    HStack(spacing: 8) { signalItems }
                }
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        structureItems
                        signalItems
                    }
                }
            }
            Text(L("虚线=未确认"))
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
        }
    }

    @ViewBuilder
    private var structureItems: some View {
        item(Theme.stroke, "笔", isOn: $vm.showStrokes)
        item(Theme.segment, "线段", isOn: $vm.showSegments)
        item(Theme.pivotFill, "中枢", isOn: $vm.showPivots)
    }

    @ViewBuilder
    private var signalItems: some View {
        // 顶底分型沿用原先同一个图层开关，两种颜色一起保留。
        item(Theme.topFractal, "分型", isOn: $vm.showFractals, secondaryColor: Theme.bottomFractal)
        item(Theme.up, "买卖点", isOn: $vm.showSignals, secondaryColor: Theme.down)
        item(Theme.divergence, "背驰", isOn: $vm.showDivergences)
    }

    private func item(
        _ color: Color, _ title: String, isOn: Binding<Bool>, secondaryColor: Color? = nil
    ) -> some View {
        Toggle(isOn: isOn) {
            HStack(spacing: 4) {
                VStack(spacing: 2) {
                    Capsule().fill(color).frame(width: 10, height: 3)
                    if let secondaryColor {
                        Capsule().fill(secondaryColor).frame(width: 10, height: 3)
                    }
                }
                Text(L(title)).font(.caption2)
            }
            .foregroundStyle(isOn.wrappedValue ? Theme.textPrimary : Theme.textSecondary)
            .opacity(isOn.wrappedValue ? 1 : 0.45)
            .padding(.horizontal, 6)
            .padding(.vertical, 6)
            .background(isOn.wrappedValue ? Theme.accent.opacity(0.12) : .clear, in: Capsule())
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .toggleStyle(ChartLayerToggleStyle())
        .allowsHitTesting(!isStatic)
    }
}
