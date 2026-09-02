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
    static func compute(screenshotSize: CGSize) -> Metrics {
        let w = screenshotSize.width
        let h = screenshotSize.height

        let banner = CGRect(x: 0, y: 0, width: w, height: bannerHeight)
        let shot = CGRect(x: 0, y: bannerHeight, width: w, height: h)
        let disclaimer = CGRect(x: 0, y: bannerHeight + h, width: w, height: disclaimerHeight)

        return Metrics(
            totalSize: CGSize(width: w, height: bannerHeight + h + disclaimerHeight),
            bannerRect: banner,
            screenshotRect: shot,
            disclaimerRect: disclaimer
        )
    }
}
