import CoreGraphics

/// 分享图的几何计算。
///
/// 刻意只依赖 CoreGraphics，不碰 UIKit/SwiftUI：本工程没有 XCTest target，
/// 测试靠 swiftc 在 macOS 命令行下编译真实源文件（见 run-share-layout-tests.sh），
/// 那里 UIKit 不可用。把几何单独拆出来，这部分才测得了。
enum ShareLayout {
    /// 品牌脚高度（图标 + 名称 + slogan + 二维码）。
    ///
    /// 放在截图下方而非上方：内容是主体、品牌是署名，先看图再看到是谁出的图；
    /// 长图场景下品牌在顶部会随滚动消失，在底部则始终收尾。
    static let footerHeight: CGFloat = 88
    /// 免责条高度。一行小字，紧贴品牌脚底部，够用即可。
    static let disclaimerHeight: CGFloat = 24
    /// 分享图四周的留白。截图卡片与品牌卡片都缩进这么多，两者左右边缘对齐。
    static let outerPadding: CGFloat = 12
    /// 截图卡片与品牌脚之间的间距。
    ///
    /// 刻意比外围留白更小：这一段是「图 → 署名」的连续阅读，间距大了会显得
    /// 品牌与内容脱节（用户反馈过 12pt 仍嫌远，收到 8）。
    static let gap: CGFloat = 8
    /// 截图卡片的圆角。
    static let screenshotCornerRadius: CGFloat = 10

    /// 一张分享图里三块内容的位置。
    ///
    /// 不叫 `Result`：那会遮蔽标准库的 `Result<Success, Failure>`，本文件日后若出现
    /// 未加限定的 `Result` 就会被这个嵌套类型截获，类型对不上时很难一眼看出原因。
    struct Metrics {
        let totalSize: CGSize
        let screenshotRect: CGRect
        let footerRect: CGRect
        let disclaimerRect: CGRect
    }

    /// 按截图尺寸算出整图布局：截图卡片在上、品牌脚与免责条在下。
    ///
    /// 宽度完全跟随截图，不写死 375：全屏图表页是横屏，截出来是横图。
    ///
    /// 截图与品牌区是**两张等宽卡片**，都缩进 `outerPadding`、左右边缘对齐。
    /// 早先品牌脚通栏、截图缩进，两者宽度差了 `outerPadding * 2`，成图上是一道
    /// 明显的错位台阶（用户反馈）。四周留白一致才像同一张卡片的上下两部分。
    static func compute(screenshotSize: CGSize) -> Metrics {
        let w = screenshotSize.width
        let h = screenshotSize.height
        let totalWidth = w + outerPadding * 2

        let shot = CGRect(x: outerPadding, y: outerPadding, width: w, height: h)
        let footer = CGRect(x: outerPadding, y: shot.maxY + gap, width: w, height: footerHeight)
        // 免责条紧贴品牌脚：同属「图之后的说明区」，中间再塞间距会把责任声明
        // 从署名区里孤立出去。两者合起来被 ShareComposer 当一张卡片裁圆角。
        let disclaimer = CGRect(x: outerPadding, y: footer.maxY, width: w, height: disclaimerHeight)

        return Metrics(
            // 底部同样收 outerPadding，四周留白才对称
            totalSize: CGSize(width: totalWidth, height: disclaimer.maxY + outerPadding),
            screenshotRect: shot,
            footerRect: footer,
            disclaimerRect: disclaimer
        )
    }
}
