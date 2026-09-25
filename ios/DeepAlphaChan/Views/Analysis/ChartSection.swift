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
                // 主图不标次级别下钻区间：最右两根K线铺浅底没有说明，看起来像莫名的阴影；
                // 次级别结论已在下方 SubLevelBar 一行写明，区间只在弹出的 30 分钟图里标。
                ChanChartView(analysis: analysis, vm: vm,
                              onFullscreen: isStatic ? nil : onFullscreen)
            }

            SubLevelBar(vm: vm, isStatic: isStatic)
        }
    }
}
