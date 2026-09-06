import SwiftUI
import DeepAlphaBaZiCore

/// 有本地生辰档案直接进已排盘首页，没有则先填表。
/// 底部 Tab 栏（八字 / 我的）留给后续 Plan C 接入登录/订阅时再引入。
struct RootView: View {
    @Environment(BaziViewModel.self) private var baziVM

    var body: some View {
        NavigationStack {
            // 本地档案还没查完之前不能直接当"没有档案"处理，否则老用户每次冷启动
            // 都会先看到一闪而过的空生辰表单，等异步查询结束才跳回已排盘首页。
            if !baziVM.hasLoadedLocalProfile {
                ProgressView()
            } else if baziVM.profile != nil {
                ChartHomeView()
            } else {
                BirthInfoFormView()
            }
        }
    }
}
