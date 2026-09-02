import SwiftUI
import UIKit

/// 分享文案。
///
/// 原先这里还有一个 `render(analysis:vm:window:)`，把图表和统计重新排版成一张
/// 375pt 固定宽的「精排卡」。已删除：那张图与用户屏幕上看到的不是一回事，
/// 现在改为截屏所见即所得（WindowCapture + ShareComposer）。
@MainActor
enum ShareCardRenderer {
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

/// 系统分享面板。由 `SharePreviewSheet` 在用户看过预览、点了「分享」后才呈现。
///
/// 没用 `ShareLink`：它要求分享内容在视图构建时就已存在，等于每次进页面都先白截一张图。
/// 这里改成需要时才生成，再把结果喂给 UIActivityViewController。
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
