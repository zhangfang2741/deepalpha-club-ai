import SwiftUI

/// 紧贴 K 线图上方的图例 + K 线图（全屏按钮在主图左上角）+ 次级别入口。
struct ChartSection: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    /// 点全屏。编排（先转屏再呈现）在调用方，这里只管发信号。
    let onFullscreen: () -> Void
    /// 离屏渲染分享长图时置 true，见 ResultDetailView.pageContent(isStatic:)。
    var isStatic = false

    var body: some View {
        VStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 10) {
                // 图例（兼图层开关）在 K 线图正上方，先看懂颜色再看图
                ChartLegend(vm: vm, isStatic: isStatic)
                ChanChartView(analysis: analysis, vm: vm, highlightFrom: drillFrom,
                              onFullscreen: isStatic ? nil : onFullscreen)
            }

            SubLevelBar(vm: vm, isStatic: isStatic)
        }
    }

    /// 大级别图上标出次级别下钻区间：最近 2 根K线（日线 ≈ 30 分钟看的近 2 个交易日，
    /// 周线 ≈ 日线看的近两周）。
    private var drillFrom: String? {
        guard vm.freq == "daily" || vm.freq == "weekly", vm.subLevel != nil else { return nil }
        let candles = analysis.mergedCandles
        guard candles.count >= 2 else { return nil }
        return candles[candles.count - 2].time
    }
}
