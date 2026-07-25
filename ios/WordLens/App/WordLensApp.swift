// App/WordLensApp.swift
import SwiftUI

@main
struct WordLensApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
