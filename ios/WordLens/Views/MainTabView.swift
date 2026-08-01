// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var nav: AppNavigationState
    /// 连播按钮嵌在 tab bar 正中间，得由这一层持有复习状态才够得着它。
    /// 首页的卡片视图共用同一个实例（通过 environmentObject 往下传）。
    @StateObject private var reviewVM = ReviewViewModel()

    var body: some View {
        ZStack {
            // 系统 TabView 的 tab bar 没法往中间塞一个自定义按钮（tabItem 只接受
            // 图标+文字），所以这里自己画 tab bar：内容区仍用 TabView 承载各页面，
            // 但把它自带的 tab bar 藏掉（.tabViewStyle(.page) 会改变手势语义，
            // 用 .toolbar(.hidden, for: .tabBar) 只隐藏视觉、保留页面切换）。
            TabView(selection: $nav.selectedTab) {
                ReviewCardView(viewModel: reviewVM)
                    .tag(MainTab.review)
                    .toolbar(.hidden, for: .tabBar)

                CameraCaptureView()
                    .tag(MainTab.camera)
                    .toolbar(.hidden, for: .tabBar)

                HomeView()
                    .tag(MainTab.vocabulary)
                    .toolbar(.hidden, for: .tabBar)

                NavigationStack {
                    SettingsView()
                }
                .tag(MainTab.settings)
                .toolbar(.hidden, for: .tabBar)
            }
            .tint(Theme.accent)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                customTabBar
            }
            .disabled(nav.blockingOperationMessage != nil)

            if let message = nav.blockingOperationMessage {
                blockingOverlay(message)
            }
        }
        .environmentObject(reviewVM)
    }

    /// 自定义 tab bar：四个页签 + 正中间一个圆形连播键（左右各两个页签，
    /// 播放键正好落在几何中心）。
    private var customTabBar: some View {
        HStack(spacing: 0) {
            tabButton(.review, label: "首页", systemImage: "house.fill")
            tabButton(.camera, label: "拍照", systemImage: "camera.fill")

            playButton

            tabButton(.vocabulary, label: "生词库", systemImage: "book.fill")
            tabButton(.settings, label: "设置", systemImage: "gearshape.fill")
        }
        .padding(.top, 8)
        .padding(.horizontal, 4)
        .background(alignment: .top) {
            // 顶部一根细分隔线 + 毛玻璃，跟系统 tab bar 的观感对齐。
            VStack(spacing: 0) {
                Divider().overlay(Theme.border)
                Rectangle().fill(.ultraThinMaterial)
            }
            .ignoresSafeArea(edges: .bottom)
        }
    }

    private func tabButton(_ tab: MainTab, label: String, systemImage: String) -> some View {
        let isSelected = nav.selectedTab == tab
        return Button {
            nav.selectedTab = tab
        } label: {
            VStack(spacing: 4) {
                Image(systemName: systemImage)
                    .font(.system(size: 20))
                Text(label)
                    .font(.system(size: 10, weight: isSelected ? .semibold : .regular))
            }
            .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }

    /// 中间的连播键：白色描边圆圈，播放中变成停止图标并填充主题色。
    /// 队列为空时（还没加载完 / 这一组没词）置灰不可点。
    private var playButton: some View {
        let isPlaying = reviewVM.autoplay.isPlaying
        let isEnabled = !reviewVM.queue.isEmpty
        return Button {
            // 在别的 tab 上按连播，顺带切回首页——否则声音在响、屏幕上却看不到
            // 是哪个词，很容易以为出问题了。
            if nav.selectedTab != .review { nav.selectedTab = .review }
            reviewVM.autoplay.toggle()
        } label: {
            Image(systemName: isPlaying ? "stop.fill" : "play.fill")
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(isEnabled ? (isPlaying ? .white : Theme.accent) : Theme.textSecondary.opacity(0.5))
                .frame(width: 52, height: 52)
                .background(
                    Circle().fill(isPlaying ? Theme.accent : Theme.surface)
                )
                .overlay(
                    Circle().strokeBorder(
                        isEnabled ? Theme.accent.opacity(isPlaying ? 0 : 0.8) : Theme.border,
                        lineWidth: 2
                    )
                )
                .shadow(color: isPlaying ? Theme.accent.opacity(0.4) : .clear, radius: 8, x: 0, y: 3)
        }
        .buttonStyle(.pressable)
        .disabled(!isEnabled)
        .frame(maxWidth: .infinity)
        // 圆比页签高，往上顶一点让它"浮"在 tab bar 上，跟音乐 App 一个观感。
        .offset(y: -6)
        .accessibilityLabel(isPlaying ? "停止连播" : "开始连播")
    }

    private func blockingOverlay(_ message: String) -> some View {
        ZStack {
            Color.black.opacity(0.32)
                .ignoresSafeArea()

            VStack(spacing: 14) {
                ProgressView()
                    .tint(Theme.accent)
                    .scaleEffect(1.15)
                Text(message)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Text("请稍等，不要关闭应用")
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
            }
            .padding(22)
            .frame(maxWidth: 260)
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 14))
        }
        .transition(.opacity)
        .zIndex(10)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isModal)
    }
}
