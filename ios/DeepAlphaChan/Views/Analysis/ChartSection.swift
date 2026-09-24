import SwiftUI

/// K 线图（图例悬浮在主图左上角）+ 次级别入口 + 全屏入口。
struct ChartSection: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    /// 点全屏。编排（先转屏再呈现）在调用方，这里只管发信号。
    let onFullscreen: () -> Void
    /// 离屏渲染分享长图时置 true，见 ResultDetailView.pageContent(isStatic:)。
    var isStatic = false

    var body: some View {
        VStack(spacing: 10) {
            SubLevelBar(vm: vm, isStatic: isStatic)

            ChanChartView(analysis: analysis, vm: vm, highlightFrom: drillFrom,
                          showsLegend: true, staticLegend: isStatic)
                .overlay(alignment: .topTrailing) {
                    if !isStatic { fullscreenButton }
                }
        }
    }

    /// 日线图上标出次级别下钻区间：最近 2 根K线（≈ 30 分钟判断所看的最近 2 个交易日）。
    private var drillFrom: String? {
        guard vm.freq == "daily", vm.subLevel != nil else { return nil }
        let candles = analysis.mergedCandles
        guard candles.count >= 2 else { return nil }
        return candles[candles.count - 2].time
    }

    private var fullscreenButton: some View {
        Button(action: onFullscreen) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.accent)
                .frame(width: 24, height: 24)
                .background(Theme.surfaceAlt.opacity(0.85), in: Circle())
                // 视觉尺寸缩小，点击区域仍保留 44pt。
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // 纯图标按钮必须给 label，否则 VoiceOver 只会念出「按钮」
        .accessibilityLabel(L("全屏查看图表"))
        .accessibilityHint(L("横屏显示，可看到更多 K 线"))
    }
}
