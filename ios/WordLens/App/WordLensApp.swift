// App/WordLensApp.swift
import SwiftUI

@main
struct WordLensApp: App {
    @StateObject private var auth = AuthViewModel()
    @StateObject private var nav = AppNavigationState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .environmentObject(nav)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
