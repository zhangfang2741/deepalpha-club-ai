// App/WordLensApp.swift
import SwiftUI

@main
struct WordLensApp: App {
    @StateObject private var auth = AuthViewModel()
    @StateObject private var nav = AppNavigationState()
    @StateObject private var localization = LocalizationManager.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(nav)
                .environmentObject(localization)
                // 切换语言时把新的 locale 注入环境，所有 Text 字面量随之重查
                // Localizable.strings；再用 .id 强制整棵视图树重建，避免个别
                // 视图缓存了旧语言的字符串没刷新。
                .environment(\.locale, localization.locale)
                .id(localization.language)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
