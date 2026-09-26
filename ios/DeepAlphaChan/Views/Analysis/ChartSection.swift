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
        VStack(alignment: .leading, spacing: 8) {
            // 图例（兼图层开关）在 K 线图正上方，先看懂颜色再看图；竖屏用紧凑一行
            ChartLegend(vm: vm, isStatic: isStatic, compact: true)
            // 主图不标次级别下钻区间：最右两根K线铺浅底没有说明，看起来像莫名的阴影；
            // 次级别结论在上方结论卡的「30 分钟确认」格里，区间只在弹出的 30 分钟图里标。
            // 竖屏不画 MACD（背驰按力度判定，MACD 不参与），全屏图里仍有。
            ChanChartView(analysis: analysis, vm: vm, showsMACD: false,
                          onFullscreen: isStatic ? nil : onFullscreen)
        }
    }
}
