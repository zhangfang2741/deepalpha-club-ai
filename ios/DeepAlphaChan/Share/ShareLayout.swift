import CoreGraphics

/// 分享图的几何计算。
///
/// 刻意只依赖 CoreGraphics，不碰 UIKit/SwiftUI：本工程没有 XCTest target，
/// 测试靠 swiftc 在 macOS 命令行下编译真实源文件（见 run-share-layout-tests.sh），
/// 那里 UIKit 不可用。把几何单独拆出来，这部分才测得了。
enum ShareLayout {
    /// 品牌头高度（App 图标 + 名称 + slogan + 二维码）。
    static let bannerHeight: CGFloat = 88
    /// 免责条高度。一行小字，够用即可。
    static let disclaimerHeight: CGFloat = 24
    /// 截图卡片左右两侧的留白。
    static let outerPadding: CGFloat = 12
    /// 品牌头↔截图、截图↔免责条之间的间距。
    static let gap: CGFloat = 12
    /// 截图卡片的圆角。
    static let screenshotCornerRadius: CGFloat = 10

    /// 一张分享图里三块内容的位置。
    ///
    /// 不叫 `Result`：那会遮蔽标准库的 `Result<Success, Failure>`，本文件日后若出现
    /// 未加限定的 `Result` 就会被这个嵌套类型截获，类型对不上时很难一眼看出原因。
    struct Metrics {
        let totalSize: CGSize
        let bannerRect: CGRect
        let screenshotRect: CGRect
        let disclaimerRect: CGRect
    }

    /// 按截图尺寸算出整图布局。
    ///
    /// 宽度完全跟随截图，不写死 375：全屏图表页是横屏，截出来是横图。
    ///
    /// 截图被当成一张「卡片」内嵌：左右缩进 `outerPadding`、上下各留 `gap`，
    /// 品牌头与免责条则通栏。三块紧贴时品牌头(#141A24)与截图顶部导航栏(#0B0E14)
    /// 色差太小会糊成一片，靠留白把边界显式画出来。
    static func compute(screenshotSize: CGSize) -> Metrics {
        let w = screenshotSize.width
        let h = screenshotSize.height
        let totalWidth = w + outerPadding * 2

        let banner = CGRect(x: 0, y: 0, width: totalWidth, height: bannerHeight)
        let shot = CGRect(x: outerPadding, y: bannerHeight + gap, width: w, height: h)
        let disclaimer = CGRect(x: 0, y: shot.maxY + gap, width: totalWidth, height: disclaimerHeight)

        return Metrics(
            totalSize: CGSize(width: totalWidth, height: disclaimer.maxY),
            bannerRect: banner,
            screenshotRect: shot,
            disclaimerRect: disclaimer
        )
    }
}
