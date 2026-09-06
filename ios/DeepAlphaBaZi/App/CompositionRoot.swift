import Foundation
import DeepAlphaBaZiCore

/// 全部依赖在此组装（视图层不直接 new service）。
@MainActor
final class CompositionRoot {
    static let apiBaseURL = URL(string: "https://api.deepalpha.club")!

    let baziVM: BaziViewModel

    init() {
        let api = APIClient(baseURL: Self.apiBaseURL)
        let service = BaziService(api: api)
        let store = BaziLocalStoreDefault.make()
        self.baziVM = BaziViewModel(service: service, store: store)
    }
}
