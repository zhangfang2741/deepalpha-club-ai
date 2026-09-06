import SwiftUI
import DeepAlphaBaZiCore

/// 有本地生辰档案直接进已排盘首页，没有则先填表。
/// 底部 Tab 栏（八字 / 我的）留给后续 Plan C 接入登录/订阅时再引入。
struct RootView: View {
    @Environment(BaziViewModel.self) private var baziVM

    var body: some View {
        NavigationStack {
            if baziVM.profile != nil {
                ChartHomeView()
            } else {
                BirthInfoFormView()
            }
        }
    }
}
