import SwiftUI
import UIKit

/// 分享面板附带的文字。
@MainActor
enum ShareText {
    /// 一句话文案（微信等会把它作为消息文字）。
    ///
    /// 末尾必须带免责语：`UIActivityViewController` 同时传图和文时，很多目标 App
    /// （含微信）只取其一 —— 落到只有文字的那一侧，这行不带风险说明的
    /// 「AAPL · 日线 | 看多」就是唯一传出去的内容。图里的免责条管不到这半边。
    static func share(analysis: ChanAnalysis, vm: ChanViewModel) -> String {
        let freq = vm.freq == "weekly" ? L("周线") : L("日线")
        let bias: String
        if let rec = analysis.recommendation {
            bias = SignalFormatting.biasLabel(rec.bias)
        } else {
            bias = SignalFormatting.trendLabel(analysis.currentTrend)
        }
        return "\(analysis.symbol.uppercased()) · \(freq) | \(bias) | DeepAlpha \(L("缠论"))"
            + " | \(L("仅供技术研究，不构成投资建议"))"
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
