// Views/Components/ScanningOverlay.swift
import SwiftUI
import UIKit

/// 拍照识别中的扫描态：叠加扫描线动画 + 状态文案。
///
/// 后端识别流会在半途推送已识别出的候选词数量（`partialWordCount`），拿到
/// 第一批之后就展示真实的"已识别到 N 个词"，比一直轮播猜测性文案更能让人
/// 安心；在还没收到任何 partial 之前（纯看图识别阶段，通常 1~2 秒）仍然用
/// 轮播文案兜底，避免裸转圈让人怀疑卡死。
struct ScanningOverlay: View {
    let image: UIImage?
    var partialWordCount: Int = 0

    @State private var scanDown = false
    @State private var messageIndex = 0

    private let messages = ["正在识别文字…", "正在生成音标…", "正在整理释义与例句…", "快好了…"]

    var body: some View {
        VStack(spacing: 20) {
            GeometryReader { geo in
                ZStack(alignment: .top) {
                    if let image {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                            .frame(width: geo.size.width, height: geo.size.height)
                            .clipped()
                            .overlay { Theme.background.opacity(0.35) }
                    } else {
                        Theme.surface
                    }

                    LinearGradient(
                        colors: [.clear, Theme.accent.opacity(0.9), .clear],
                        startPoint: .leading, endPoint: .trailing
                    )
                    .frame(width: geo.size.width, height: 3)
                    .shadow(color: Theme.accent.opacity(0.8), radius: 6)
                    .offset(y: scanDown ? geo.size.height : 0)
                }
                .clipShape(.rect(cornerRadius: 16))
                .onAppear {
                    withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                        scanDown = true
                    }
                }
            }
            .frame(height: 280)
            .padding(.horizontal)

            // 用 if/else 分成两个结构上独立的分支，而不是在一个 Text 里用三元
            // 表达式切字符串：后者依赖 SwiftUI 对同一个 Text 节点做内容 diff，
            // 叠加 .contentTransition/.animation 时实测不可靠；分支切换是视图
            // 身份变化，更新一定会走到。
            //
            // 视觉上也刻意跟灰色轮播文案拉开（主题色 + 加粗 + 大一号字），
            // 否则"已识别到 N 个词，正在整理释义…"跟轮播里的"正在整理释义与
            // 例句…"长得太像，数字在跳也容易被当成没变化。
            if partialWordCount > 0 {
                VStack(spacing: 4) {
                    HStack(spacing: 6) {
                        Image(systemName: "text.badge.checkmark")
                        // monospacedDigit：数字位宽固定，快速跳动时不会左右抖。
                        Text("已识别 \(partialWordCount) 个词")
                            .monospacedDigit()
                    }
                    .font(.title3.weight(.bold))
                    .foregroundStyle(Theme.accent)

                    Text("正在整理音标与释义…")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                .onChange(of: partialWordCount) { _, newValue in
                    // 临时探针：用来区分"视图没收到更新"和"收到了但没渲染出来"。
                    print("[ScanningOverlay] rendered partialWordCount = \(newValue)")
                }
            } else {
                Text(messages[messageIndex])
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                    .task {
                        while !Task.isCancelled {
                            try? await Task.sleep(for: .seconds(1.8))
                            withAnimation { messageIndex = (messageIndex + 1) % messages.count }
                        }
                    }
            }
        }
        .animation(.easeInOut(duration: 0.25), value: partialWordCount > 0)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            partialWordCount > 0
                ? "已识别到 \(partialWordCount) 个单词，正在整理释义"
                : "正在识别图片中的单词，请稍候"
        )
    }
}
