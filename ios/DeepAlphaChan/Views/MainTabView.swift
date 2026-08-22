import SwiftUI

/// 登录后的主容器。
///
/// 三个 Tab 对应三种意图：**做分析**、**学概念**、**管账号**。原本这三件事全挤在
/// 一个滚动页里，其中「管账号」还藏在右上角图标后面——删除账号是 App Store
/// 5.1.1(v) 要求的入口，不该那么难找。
struct MainTabView: View {
    var body: some View {
        TabView {
            AnalysisTabView()
                .tabItem { Label("分析", systemImage: "chart.xyaxis.line") }

            LearnTabView()
                .tabItem { Label("学习", systemImage: "book") }

            ProfileView()
                .tabItem { Label("我的", systemImage: "person.circle") }
        }
    }
}
