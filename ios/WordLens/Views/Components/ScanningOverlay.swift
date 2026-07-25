// Views/Components/ScanningOverlay.swift
import SwiftUI
import UIKit

/// 拍照识别中的扫描态：叠加扫描线动画 + 轮播状态文案。
///
/// 识别是一次性 LLM 请求，没有真实的分阶段进度可以展示；裸转圈在等待较久时
/// （长词表偶尔要重试）容易让人怀疑卡死了。用扫描线 + 轮播文案做"感知进度"，
/// 让用户知道系统还在动，不代表精确的完成百分比。
struct ScanningOverlay: View {
    let image: UIImage?

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

            Text(messages[messageIndex])
                .font(.subheadline)
                .foregroundStyle(Theme.textSecondary)
                .contentTransition(.opacity)
                .task {
                    while !Task.isCancelled {
                        try? await Task.sleep(for: .seconds(1.8))
                        withAnimation { messageIndex = (messageIndex + 1) % messages.count }
                    }
                }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("正在识别图片中的单词，请稍候")
    }
}
