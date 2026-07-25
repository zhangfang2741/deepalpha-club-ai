// App/AppNavigationState.swift
import Foundation

enum MainTab: Hashable {
    case review, camera, vocabulary, settings
}

/// 跨 tab 的导航/高亮状态。拍照识别加入生词库后要跳到"生词库" tab 并高亮
/// 刚加入的词——这两步分别发生在 CameraCaptureView 的 sheet 里和 HomeView
/// 里，中间隔着 TabView，没有共享状态的话没法互相通知，所以提到 App 层用
/// EnvironmentObject 广播。
@MainActor
final class AppNavigationState: ObservableObject {
    @Published var selectedTab: MainTab = .review
    @Published var highlightedWordIDs: Set<String> = []

    func showNewlyAddedWords(_ ids: [String]) {
        selectedTab = .vocabulary
        highlightedWordIDs = Set(ids)
    }

    /// 高亮是一次性提示，不需要用户手动清除；生词库页出现后过一段时间自动褪去。
    func clearHighlight() {
        highlightedWordIDs = []
    }
}
