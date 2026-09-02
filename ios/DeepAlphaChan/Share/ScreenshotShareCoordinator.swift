import Foundation

/// 截图分享的进程级协调器：全局唯一响应者 + 全局防抖。
///
/// 旧架构里每个挂载点各自用 onAppear/onDisappear 猜「我是否可见」，挡不住
/// 子视图自带的 sheet —— 呈现方收不到 onDisappear，宿主与弹层同时响应，
/// 两个 sheet 抢同一个 presenter，输掉的那个状态永远停在非 nil，本页分享
/// 从此静默失效。改成单一栈后「谁响应」只看栈顶：onAppear 的顺序天然等于
/// 「谁在最上层」，所以即使某个宿主的 onDisappear 没触发，栈顶仍然是当前
/// 真正可见的那个（或显式挡在上面的抑制层）。
@MainActor
final class ScreenshotShareCoordinator {
    static let shared = ScreenshotShareCoordinator()

    /// 后注册的在栈顶。元素是同时在屏的挂载点数量级，普通数组足够。
    private var stack: [UUID] = []

    /// 上次有挂载点真正消费截图事件的时间。系统偶尔会连发通知，0.5 秒内的重复忽略。
    private var lastFired = Date.distantPast

    /// 挂载点出现时登记。先移除同 id 再追加，防止重复入栈。
    func push(_ id: UUID) {
        stack.removeAll { $0 == id }
        stack.append(id)
    }

    /// 挂载点消失时移除。
    func remove(_ id: UUID) {
        stack.removeAll { $0 == id }
    }

    /// 本次截图事件是否由 id 指定的挂载点消费。
    ///
    /// 只放行栈顶：这保证两个页面永远不可能同时弹分享 sheet。防抖只在
    /// 通过栈顶检查后才动 —— 被否决的挂载点不消耗防抖窗口，否则一次
    /// 落选就会吞掉紧随其后的真实事件。
    func shouldHandle(_ id: UUID) -> Bool {
        guard stack.last == id else { return false }
        guard Date().timeIntervalSince(lastFired) > 0.5 else { return false }
        lastFired = Date()
        return true
    }
}
