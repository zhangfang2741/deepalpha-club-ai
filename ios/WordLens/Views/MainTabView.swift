// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var nav: AppNavigationState

    var body: some View {
        TabView(selection: $nav.selectedTab) {
            ReviewCardView()
                .tabItem { Label("首页", systemImage: "house.fill") }
                .tag(MainTab.review)

            CameraCaptureView()
                .tabItem { Label("拍照", systemImage: "camera.fill") }
                .tag(MainTab.camera)

            HomeView()
                .tabItem { Label("生词库", systemImage: "book.fill") }
                .tag(MainTab.vocabulary)

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label("设置", systemImage: "gearshape.fill") }
            .tag(MainTab.settings)
        }
        .tint(Theme.accent)
    }
}
