import SwiftUI
import UIKit

/// 把截图拼成最终分享图：截图卡片在上，品牌脚 + 免责条在下。
///
/// 位置全部由 `ShareLayout` 算好，这里只负责画。分工是为了让几何部分能在
/// 没有 UIKit 的命令行测试里跑（见 ShareLayout.swift 注释）。
@MainActor
enum ShareComposer {
    /// 拼图。
    ///
    /// - Parameter screenshot: `WindowCapture.capture()` 的产物。
    /// - Returns: 失败返回 nil，调用方静默放弃 —— 用户只是截了个图，
    ///   为一个他没主动发起的功能弹错误框很打扰。
    static func compose(screenshot: UIImage) -> UIImage? {
        let layout = ShareLayout.compute(screenshotSize: screenshot.size)

        // 品牌脚/免责条按截图自身的 scale 渲染，而不是 UIScreen.main.scale：
        // 最终画布（下方 format.scale）也取 screenshot.scale，三块内容像素密度
        // 对齐才不会一块清晰一块糊；用截图自带的 scale 还省得依赖已在 iOS 16
        // 弃用、且在多屏/无主屏场景下不可靠的 UIScreen.main。
        guard let footer = render(ShareFooter(width: layout.footerRect.width),
                                  size: layout.footerRect.size,
                                  scale: screenshot.scale),
              let disclaimer = render(ShareDisclaimer(width: layout.disclaimerRect.width),
                                      size: layout.disclaimerRect.size,
                                      scale: screenshot.scale)
        else { return nil }

        // 按截图自身的 scale 输出，保证拼接后不糊
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = screenshot.scale
        let renderer = UIGraphicsImageRenderer(size: layout.totalSize, format: format)

        return renderer.image { ctx in
            // 先铺满底色再画三块。留白与 gap 会露出画布，
            // 不填的话那些像素是透明的，分享到微信时 PNG 会被转成 JPEG，
            // 透明通道按黑或白展平，出来就是几道突兀的色带。
            UIColor(Theme.background).setFill()
            ctx.fill(CGRect(origin: .zero, size: layout.totalSize))

            // 截图按圆角裁剪，看起来像被托住的一张卡片。裁剪区会一直作用到
            // context 结束，必须存档/还原，否则下方的品牌脚/免责条也会被裁掉。
            ctx.cgContext.saveGState()
            UIBezierPath(roundedRect: layout.screenshotRect,
                         cornerRadius: ShareLayout.screenshotCornerRadius).addClip()
            screenshot.draw(in: layout.screenshotRect)
            ctx.cgContext.restoreGState()

            // 品牌脚与免责条合起来当第二张卡片：与截图等宽、同圆角。
            // 分开各画各的会在两者之间露出直角，看着像两个拼歪的色块。
            ctx.cgContext.saveGState()
            UIBezierPath(roundedRect: layout.footerRect.union(layout.disclaimerRect),
                         cornerRadius: ShareLayout.screenshotCornerRadius).addClip()
            footer.draw(in: layout.footerRect)
            disclaimer.draw(in: layout.disclaimerRect)
            ctx.cgContext.restoreGState()
        }
    }

    /// 把 SwiftUI 视图离屏渲染成位图。
    private static func render<V: View>(_ view: V, size: CGSize, scale: CGFloat) -> UIImage? {
        let renderer = ImageRenderer(content: view.frame(width: size.width, height: size.height))
        renderer.scale = scale
        return renderer.uiImage
    }
}
