// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("生词库", systemImage: "book.fill") }

            CameraCaptureView()
                .tabItem { Label("拍照", systemImage: "camera.fill") }

            ReviewCardView()
                .tabItem { Label("复习", systemImage: "arrow.triangle.2.circlepath") }
        }
        .tint(Theme.accent)
    }
}
