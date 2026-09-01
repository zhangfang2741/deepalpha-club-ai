import SwiftUI

/// 分享卡：一张自带品牌与下载二维码的分析图。
///
/// 只做呈现，不持有任何状态——所有数据由参数传入，因此既能离屏渲染成图片，
/// 也能在 Preview 里直接目视排版。
///
/// 尺寸固定为 `designWidth`（375pt，iPhone 标准宽度），不跟随屏幕：分享图的构图
/// 必须可预期，不能因为用户用的是 iPhone SE 还是 Pro Max 而排版两样。
struct ShareCardView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    /// 用户当前看到的图表窗口。nil = 用图表默认窗口（最新那一段）。
    let window: ChartWindow?

    /// 分享卡设计宽度。渲染时按 scale 倍率放大成位图。
    static let designWidth: CGFloat = 375

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            chart
            conclusion
            stats
            Divider().background(Theme.border)
            footer
        }
        .padding(16)
        .frame(width: Self.designWidth)
        .background(Theme.background)
    }

    // MARK: - 标题栏

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(analysis.symbol.uppercased())
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(Theme.textPrimary)
            Text(freqLabel)
                .font(.system(size: 13))
                .foregroundColor(Theme.textSecondary)
            Spacer()
            Text("DeepAlpha")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.accent)
        }
    }

    private var freqLabel: String {
        vm.freq == "weekly" ? L("周线") : L("日线")
    }

    // MARK: - 图表

    /// 复用主图表，但关掉交互：分享图里不该留着十字光标，也不需要手势。
    /// 窗口透传，保证「分享出去的那一段 = 用户看到的那一段」。
    private var chart: some View {
        ChanChartView(analysis: analysis,
                      vm: vm,
                      initialWindow: window,
                      interactive: false)
    }

    // MARK: - 结论摘要

    private var conclusion: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(biasText)
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(biasColor)

            // headline 缺失时退回 summary，与「形态分析」段的取值口径保持一致
            Text(analysis.narrative?.headline ?? analysis.summary)
                .font(.system(size: 13))
                .foregroundColor(Theme.textPrimary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// 优先用加权后的多空倾向；结构没成形时退回趋势——同 AnalysisSection 的 chip 逻辑。
    private var biasText: String {
        if let rec = analysis.recommendation {
            return SignalFormatting.biasLabel(rec.bias)
        }
        return SignalFormatting.trendLabel(analysis.currentTrend)
    }

    private var biasColor: Color {
        if let rec = analysis.recommendation {
            return SignalFormatting.biasColor(rec.bias)
        }
        return SignalFormatting.trendColor(analysis.currentTrend)
    }

    // MARK: - 结构统计

    private var stats: some View {
        Text(statsText)
            .font(.system(size: 11))
            .foregroundColor(Theme.textSecondary)
    }

    private var statsText: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    // MARK: - 页脚：免责声明 + 二维码

    /// 免责声明必须留在图上。分享图会脱离 App 语境传播，被当成荐股截图转发时，
    /// 这行字是唯一还跟着图走的风险说明。
    private var footer: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
                    .font(.system(size: 10))
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(L("扫码下载 DeepAlpha 缠论"))
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Theme.textPrimary)
            }
            Spacer(minLength: 0)
            qrCode
        }
    }

    @ViewBuilder
    private var qrCode: some View {
        if let qr = QRCode.image(for: AppConfig.downloadPageURL, side: 56) {
            Image(uiImage: qr)
                .resizable()
                .frame(width: 56, height: 56)
                // 白色内边距是二维码的「静默区」，紧贴深色底会明显掉识别率
                .padding(4)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }
}

#if DEBUG
#Preview("分享卡") {
    ShareCardView(analysis: PreviewMock.analysis,
                  vm: ChanViewModel(),
                  window: nil)
        .padding()
        .background(Color.black)
}
#endif
