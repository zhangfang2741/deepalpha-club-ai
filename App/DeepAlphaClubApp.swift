import SwiftUI
import DeepAlphaCore

@main
struct DeepAlphaClubApp: App {
    @State private var root = CompositionRoot()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(\.compositionRoot, root)
                .environment(root.appState)
                .environment(root.deskVM)
                .environment(root.historyVM)
                .task {
                    root.appState.restoreFromKeychain()
                }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .background:
                root.deskVM.appDidEnterBackground()
            case .active:
                Task { await root.deskVM.appDidBecomeActive() }
            default:
                break
            }
        }
    }
}
