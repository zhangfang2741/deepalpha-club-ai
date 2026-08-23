import SwiftUI

/// 全屏图表。竖屏横屏都能看，横过来能显示更多 K 线。
///
/// 图表高度按可用空间算而不是用默认的 300pt——写死高度的话「全屏」只是换了个
/// 黑底，图还是那么大，等于没做。
struct ChartFullscreenView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    @EnvironmentObject private var orientation: AppOrientation
    @Environment(\.dismiss) private var dismiss

    /// 顶栏 + 图层开关 + 图例 + 上下留白占掉的高度，剩下的全给图表。
    private let chromeHeight: CGFloat = 132
    /// 主图与 MACD 的高度配比。副图给太多会挤掉主图，2.8 : 1 接近常规看盘软件。
    private let macdRatio: CGFloat = 1 / 3.8

    var body: some View {
        GeometryReader { geo in
            let available = max(220, geo.size.height - chromeHeight)
            let macdH = min(120, available * macdRatio)
            let priceH = available - macdH

            VStack(spacing: 8) {
                header
                LayerToggles(vm: vm)
                    .padding(.horizontal, 12)

                ChanChartView(analysis: analysis, vm: vm,
                              priceHeight: priceH, macdHeight: macdH)

                ChartLegend()
                    .padding(.bottom, 2)
            }
            .padding(.top, 6)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .background(Theme.background.ignoresSafeArea())
        // 转屏由调用方在呈现前完成（见 ResultDetailView.openFullscreen）。
        // 还原必须无条件做，漏了的话用户退出后整个 App 会卡在横屏。
        .onDisappear { orientation.lockPortrait() }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text(vm.symbol.uppercased())
                .font(.subheadline.bold())
                .foregroundColor(Theme.textPrimary)
            Text(vm.freq == "weekly" ? L("周线") : L("日线"))
                .font(.caption)
                .foregroundColor(Theme.accent)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Capsule())

            Spacer()

            Button {
                // 与打开时对称：关掉滑落动画，退出时只剩系统那一次旋转
                var tx = Transaction()
                tx.disablesAnimations = true
                withTransaction(tx) { dismiss() }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title3)
                    .foregroundColor(Theme.textSecondary)
            }
            .accessibilityLabel("退出全屏")
        }
        .padding(.horizontal, 14)
    }
}
