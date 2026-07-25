// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            ReviewCardView()
                .tabItem { Label("首页", systemImage: "house.fill") }

            CameraCaptureView()
                .tabItem { Label("拍照", systemImage: "camera.fill") }

            HomeView()
                .tabItem { Label("生词库", systemImage: "book.fill") }

            NavigationStack {
                SettingsView()
            }
            .tabItem { Label("设置", systemImage: "gearshape.fill") }
        }
        .tint(Theme.accent)
    }
}
