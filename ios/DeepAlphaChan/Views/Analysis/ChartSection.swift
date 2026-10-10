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
            ChartLegend(vm: vm, isStatic: isStatic, compact: true, analysis: analysis)
            // 主图不标次级别下钻区间：最右两根K线铺浅底没有说明，看起来像莫名的阴影；
            // 次级别结论在上方结论卡的「30 分钟确认」格里，区间只在弹出的 30 分钟图里标。
            // 竖屏也画 MACD 副图：趋势背驰比的就是 b 段与 c 段的红绿柱面积，副图上把这两段用粉色底标出来，
            // 与主图的 b / c 两条线对得上。
            // 图和指标栏贴紧（指标栏是图的一部分，不跟下面的内容挤在一起）
            VStack(alignment: .leading, spacing: 0) {
                ChanChartView(analysis: analysis, vm: vm,
                              onFullscreen: isStatic ? nil : onFullscreen)
                // 指标栏在图下方：点一下开 / 关均线、EMA、BOLL（分享长图里不放）；威科夫 / SMC 在上面图例行右侧的「对比」下拉框里
                if !isStatic { IndicatorBar(vm: vm, analysis: analysis) }
            }
        }
    }
}
