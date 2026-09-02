import SwiftUI
import UIKit

/// 把详情页整页内容离屏渲染成一张长图（分享按钮路径）。
///
/// 与 `WindowCapture` 刻意不同：截图是「用户此刻看到的窗口」，含导航栏/TabBar、
/// 只含滚动到的可视区；长图是「页面的完整内容」——直接渲染内容视图本身，
/// 不含任何系统栏，高度由内容撑开，用户没滚到的部分也在图里。
/// 两条入口产出不同的东西是需求本身，不是巧合。
@MainActor
enum PageSnapshot {
    /// 渲染整页长图。失败返回 nil，调用方决定如何提示。
    ///
    /// - Parameter content: 与屏幕显示一致、已含内边距的页面内容（不含背景，
    ///   背景在这里统一铺，保证导出的位图没有透明像素）。
    static func render<V: View>(_ content: V) -> UIImage? {
        guard let window = foregroundWindow() else { return nil }
        // 宽度对齐当前窗口：长图的换行、图表宽度才和屏幕上的一致
        let width = window.bounds.width

        func snapshot() -> some View {
            content
                .frame(width: width)
                // 不铺背景的话位图四周是透明的，转 JPEG 分享时按黑或白展平
                .background(Theme.background)
                // ImageRenderer 的环境不继承 App 根部的 preferredColorScheme(.dark)：
                // 实测（模拟器、系统亮色模式）离屏环境解析为 light，分段控件和
                // 默认前景色文字会按亮色画在深色背景上。必须显式覆写。
                .environment(\.colorScheme, .dark)
        }

        // 先用 1/4 倍率量内容高度再定档：布局按 pt 算、与 scale 无关（实测 0.25x
        // 下 point 高度精确），位图只有几十 KB。若直接按 @3x 渲染 4000pt 长的页面，
        // 会先画出 ~58MB 的位图才知道尺寸，老设备上有内存压力。
        let measurer = ImageRenderer(content: snapshot())
        measurer.scale = 0.25
        guard let probe = measurer.uiImage else { return nil }
        let height = probe.size.height

        // 按「单张位图峰值不超过 ~35MB」定档：档内能开 3x 就开 3x（与屏幕同清晰度，
        // 品牌头二维码像素最多），超长页降 2x/1.5x，肉眼几乎无差。
        // 实测（iPhone 17 Pro 模拟器，宽 402pt）：
        //   h=2000pt @3x → 1206×6000px ≈ 29MB；h=4000pt @2x → 804×8000px ≈ 26MB；
        //   h=8000pt @1.5x → 603×12000px ≈ 29MB。均远低于直接 @3x 渲染 4000pt 的 58MB。
        let scale: CGFloat
        if height <= 2400 {
            scale = 3
        } else if height <= 5200 {
            scale = 2
        } else {
            scale = 1.5
        }

        let renderer = ImageRenderer(content: snapshot())
        renderer.scale = scale
        // 超大位图 ImageRenderer 可能返回 nil（已知坑），交给调用方按失败提示
        return renderer.uiImage
    }

    /// 与 `WindowCapture.foregroundWindow` 同一取法。那份文件不归本次改动碰，
    /// 六行代码复制一份比为了复用去动它更划算。
    private static func foregroundWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }?
            .keyWindow
    }
}
