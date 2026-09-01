import SwiftUI
import UIKit

/// 把 `ShareCardView` 离屏渲染成位图。
///
/// 走 `ImageRenderer` 而不是截屏：截屏会带上导航栏、状态栏和当前滚动位置，
/// 尺寸还随机型变。离屏渲染的构图完全可预期，且能按 @3x 输出。
@MainActor
enum ShareCardRenderer {
    /// 输出倍率。分享图会被人放大看细节，@3x 起步。
    private static let scale: CGFloat = 3

    /// 渲染分享卡。
    ///
    /// - Returns: 渲染失败返回 nil。调用方必须提示用户，不要静默吞掉——
    ///   点了分享却什么都没发生，比报错更让人困惑。
    static func render(analysis: ChanAnalysis,
                       vm: ChanViewModel,
                       window: ChartWindow?) -> UIImage? {
        let card = ShareCardView(analysis: analysis, vm: vm, window: window)
        let renderer = ImageRenderer(content: card)
        renderer.scale = scale
        // 卡片自身用 .frame(width:) 固定了宽度，高度由内容撑开，这里不再提议尺寸
        return renderer.uiImage
    }

    /// 分享面板附带的一句话文案（微信等会把它作为消息文字）。
    static func shareText(analysis: ChanAnalysis, vm: ChanViewModel) -> String {
        let freq = vm.freq == "weekly" ? L("周线") : L("日线")
        let bias: String
        if let rec = analysis.recommendation {
            bias = SignalFormatting.biasLabel(rec.bias)
        } else {
            bias = SignalFormatting.trendLabel(analysis.currentTrend)
        }
        return "\(analysis.symbol.uppercased()) · \(freq) | \(bias) | DeepAlpha \(L("缠论"))"
    }
}

/// 系统分享面板。
///
/// 没用 `ShareLink`：它要求分享内容在视图构建时就已存在，等于每次进结果页都先
/// 白渲染一张图。这里改成点按才渲染，再把结果喂给 UIActivityViewController。
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
