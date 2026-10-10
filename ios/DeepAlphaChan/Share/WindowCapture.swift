import UIKit

/// 把当前前台窗口截成图片。
///
/// iOS 不提供读取用户所截图片的 API —— `userDidTakeScreenshotNotification` 只告知
/// 「刚发生了截图」，不含图像。所以收到通知后由我们自己再截一张，内容与用户所截一致，
/// 唯一差别是没有状态栏（状态栏属于系统独立 window，App 截不到），
/// 以及顶部导航栏（返回 / 标题 / 分享 / 收藏）和底部 TabBar 被有意排除（见 `contentBounds`）。
@MainActor
enum WindowCapture {
    /// TabBar 底边与窗口底边的允许间距。
    ///
    /// iOS 26 的 TabBar 是悬浮的，不再贴着屏幕底边，要求严格贴底会漏判。
    private static let tabBarBottomTolerance: CGFloat = 60

    /// 截当前前台 window。失败返回 nil，调用方静默放弃。
    static func capture() -> UIImage? {
        guard let window = foregroundWindow() else { return nil }
        let bounds = contentBounds(of: window)

        // drawHierarchy 取的是已渲染内容，比 layer.render 更贴近用户看到的画面。
        // afterScreenUpdates: false —— 通知回调里不该再触发一次重排。
        //
        // 画的范围仍是完整的 window.bounds，只有画布是裁过的：超出画布的部分自然被丢弃，
        // 省掉一次对 UIImage 的二次裁剪，也不用换算坐标。
        //
        // 裁掉顶部导航栏后 bounds 的起点不在 (0, 0)：画布固定从 (0, 0) 起，用显式平移把要截的区域挪到左上角，
        // 不依赖 UIGraphicsImageRenderer(bounds:) 对非零起点的处理。
        var succeeded = false
        let image = UIGraphicsImageRenderer(size: bounds.size).image { ctx in
            ctx.cgContext.translateBy(x: -bounds.minX, y: -bounds.minY)
            succeeded = window.drawHierarchy(in: window.bounds, afterScreenUpdates: false)
        }
        if succeeded { return image }

        // 某些图层（Metal、部分系统模糊）drawHierarchy 会返回 false。此时**另起**一个
        // renderer 而不是接着往上一个 context 里画：返回 false 只表示「没能完整渲染」，
        // 并不保证它一笔都没画过，在同一张画布上叠加 layer.render 可能糊出重影。
        // 降级路径同样用裁过的画布，否则两条路径截出来的构图会不一致。
        return UIGraphicsImageRenderer(size: bounds.size).image { ctx in
            ctx.cgContext.translateBy(x: -bounds.minX, y: -bounds.minY)
            window.layer.render(in: ctx.cgContext)
        }
    }

    /// 要截的区域：window 全幅，但顶部导航栏、底部 TabBar 当前真的可见时把它们排除在外。
    ///
    /// 分享图里出现一条导航栏 / TabBar 既没信息量也显得像误截（导航栏里是返回、分享、收藏这些按钮）。
    /// 但不能无脑砍固定高度：全屏图表页是 `fullScreenCover`，本来就没有这两条，砍了就把图表切掉一截。
    /// 所以「有就裁、没有就不裁」，裁多少也由它们自己的位置决定。
    private static func contentBounds(of window: UIWindow) -> CGRect {
        var top = window.bounds.minY
        var bottom = window.bounds.maxY

        // 裁到导航栏底边：状态栏那一截本来就截不到，导航栏底边以上整段不要
        if let navBar = visibleTopNavigationBar(in: window) {
            let maxY = navBar.convert(navBar.bounds, to: window).maxY
            if maxY > top, maxY < window.bounds.height / 2 { top = maxY }
        }

        // 裁到 TabBar 顶边。悬浮 TabBar 下方那条露出的内容也一并去掉 ——
        // 留着只会是半行被切开的列表，比直接切干净更难看。
        if let tabBar = visibleBottomTabBar(in: window) {
            let minY = tabBar.convert(tabBar.bounds, to: window).minY
            if minY > top, minY < window.bounds.maxY { bottom = minY }
        }

        guard bottom > top else { return window.bounds }
        return CGRect(x: window.bounds.minX, y: top, width: window.bounds.width, height: bottom - top)
    }

    /// 找出当前真的显示在最上层、且贴着窗口顶部的导航栏。
    ///
    /// 判定同样保守：拿不准就返回 nil（不裁）。误裁会切掉用户想分享的内容，漏裁只是多一条导航栏。
    /// 先取「最上层被呈现的控制器」再在它的视图里找：全屏图表（`fullScreenCover`）盖在上面时，
    /// 下层页面的导航栏还在视图层级里、但看不见，不能按它裁；半屏的 sheet 里自带的导航栏不贴着窗口顶部，也不会被当成。
    private static func visibleTopNavigationBar(in window: UIWindow) -> UINavigationBar? {
        guard let root = window.rootViewController else { return nil }
        var topController = root
        while let presented = topController.presentedViewController { topController = presented }

        let candidates = findNavigationBars(in: topController.view).filter { bar in
            guard !bar.isHidden, bar.alpha > 0.01 else { return false }
            let frame = bar.convert(bar.bounds, to: window)
            // 必须贴着窗口顶部：`.toolbar(.hidden, for: .navigationBar)` 在部分版本上是把导航栏平移出屏而不是置 isHidden
            return frame.height > 0 && frame.minY >= -1 && frame.maxY <= window.bounds.height * 0.4
        }
        // 嵌套时可能有多个，取最靠下的底边，保证都被排除
        return candidates.max { $0.convert($0.bounds, to: window).maxY < $1.convert($1.bounds, to: window).maxY }
    }

    /// 递归收集视图层级里的 UINavigationBar（SwiftUI 的 `NavigationStack` 底层就是 `UINavigationController`）。
    private static func findNavigationBars(in view: UIView) -> [UINavigationBar] {
        if let bar = view as? UINavigationBar { return [bar] }
        return view.subviews.flatMap(findNavigationBars)
    }

    /// 找出当前确实盖在最上层、且位于窗口底部的 TabBar。
    ///
    /// 判定刻意保守：拿不准就返回 nil（退化成裁 0，即改动前的行为）。误裁会切掉用户
    /// 真正想分享的图表内容，漏裁只是多一条 TabBar，两者代价不对等。
    private static func visibleBottomTabBar(in window: UIWindow) -> UITabBar? {
        let candidates = findTabBars(in: window).filter { tabBar in
            guard !tabBar.isHidden, tabBar.alpha > 0.01 else { return false }

            let frame = tabBar.convert(tabBar.bounds, to: window)
            // 必须在窗口下半部分且贴近底边：`.toolbar(.hidden, for: .tabBar)` 在部分
            // 版本上是把 TabBar 平移出屏而不是置 isHidden，位置检查能一并挡掉。
            guard frame.minY > window.bounds.midY,
                  frame.maxY >= window.bounds.maxY - tabBarBottomTolerance,
                  frame.maxY <= window.bounds.maxY + 1
            else { return false }

            // 有东西盖在它上面（典型是 fullScreenCover 的内容）时不裁。
            // hitTest 会跳过 isHidden / alpha 近 0 / 关掉交互的视图，命中的若不是
            // TabBar 自己或它的子视图，说明这块区域此刻显示的是别的东西。
            let probe = CGPoint(x: frame.midX, y: frame.midY)
            guard let hit = window.hitTest(probe, with: nil), hit.isDescendant(of: tabBar)
            else { return false }

            return true
        }

        // 嵌套 TabView 时可能有多个，取最靠上的那个，保证所有 TabBar 都被排除
        return candidates.min { $0.convert($0.bounds, to: window).minY
            < $1.convert($1.bounds, to: window).minY }
    }

    /// 递归收集视图层级里的 UITabBar。
    ///
    /// SwiftUI 的 `TabView` 在 iOS 上底层就是 `UITabBarController`，所以能这样找到。
    private static func findTabBars(in view: UIView) -> [UITabBar] {
        // 命中后不再往下找：TabBar 内部不会再嵌一个 TabBar
        if let tabBar = view as? UITabBar { return [tabBar] }
        return view.subviews.flatMap(findTabBars)
    }

    private static func foregroundWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }?
            .keyWindow
    }
}
