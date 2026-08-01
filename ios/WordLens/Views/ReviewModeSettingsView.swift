// Views/ReviewModeSettingsView.swift
import SwiftUI

/// 学习模式设置页（从设置页进入）。
///
/// 原来这个开关挂在首页右上角的工具栏菜单里。但它是个"设一次就基本不动"的
/// 偏好，占着首页最显眼的位置不划算——首页应该只留跟当前这张卡有关的操作。
/// 偏好仍存在 UserDefaults（`ReviewMode.current`），首页切回来时会自动同步。
struct ReviewModeSettingsView: View {
    @State private var mode: ReviewMode = ReviewMode.current

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section {
                    Picker("学习模式", selection: $mode) {
                        ForEach(ReviewMode.allCases, id: \.self) { m in
                            Text(m.label).tag(m)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                    .onChange(of: mode) { _, newValue in
                        ReviewMode.current = newValue
                    }
                } header: {
                    Text("学习模式")
                } footer: {
                    Text("只影响单词出现的先后顺序，不改变复习调度算法——什么时候该再复习一个词，始终由 SM-2 按你的评分决定。\n\n智能复习：按到期时间先后（自定义分组则按你排的顺序）；随机乱序：每次打乱；难词优先：不认识 → 模糊 → 认识；加入顺序：按加入生词库的先后。")
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("学习模式")
        .navigationBarTitleDisplayMode(.inline)
    }
}
