import SwiftUI
import DeepAlphaBaZiCore

@main
struct DeepAlphaBaZiApp: App {
    @State private var root = CompositionRoot()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(root.baziVM)
                .task {
                    await root.baziVM.loadLocalProfile()
                }
        }
    }
}
