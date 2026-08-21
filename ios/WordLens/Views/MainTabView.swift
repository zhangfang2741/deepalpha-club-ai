// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var nav: AppNavigationState

    var body: some View {
        ZStack {
            // 连播键回到学习页内部（见 ReviewCardView.transportBar）之后，这里
            // 没有再往 tab bar 中间塞按钮的需求，用回系统 TabView 就够了。
            TabView(selection: $nav.selectedTab) {
                CameraCaptureView()
                    .tabItem { Label(L("首页"), systemImage: "house.fill") }
                    .tag(MainTab.home)

                ReviewCardView()
                    .tabItem { Label(L("学习"), systemImage: "graduationcap.fill") }
                    .tag(MainTab.study)

                HomeView()
                    .tabItem { Label(L("生词库"), systemImage: "book.fill") }
                    .tag(MainTab.vocabulary)

                NavigationStack {
                    SettingsView()
                }
                .tabItem { Label(L("设置"), systemImage: "gearshape.fill") }
                .tag(MainTab.settings)
            }
            .tint(Theme.accent)
            .disabled(nav.blockingOperationMessage != nil)

            if let message = nav.blockingOperationMessage {
                blockingOverlay(message)
            }
        }
    }

    private func blockingOverlay(_ message: String) -> some View {
        ZStack {
            Color.black.opacity(0.32)
                .ignoresSafeArea()

            VStack(spacing: 14) {
                ProgressView()
                    .tint(Theme.accent)
                    .scaleEffect(1.15)
                Text(message)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text(L("请稍等，不要关闭应用"))
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
            }
            .padding(22)
            .frame(maxWidth: 260)
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 14))
        }
        .transition(.opacity)
        .zIndex(10)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isModal)
    }
}
