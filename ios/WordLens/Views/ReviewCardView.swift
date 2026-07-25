// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.queue.isEmpty {
                    ContentUnavailableView(
                        "今天没有待复习的单词",
                        systemImage: "checkmark.circle",
                        description: Text("去拍照识别一些新单词吧")
                    )
                } else if viewModel.isFinished {
                    ContentUnavailableView(
                        "今日复习完成 🎉",
                        systemImage: "star.fill",
                        description: Text("共复习了 \(viewModel.totalCount) 个单词")
                    )
                } else if let word = viewModel.currentWord {
                    cardContent(word)
                }
            }
            .navigationTitle("首页")
            .navigationBarTitleDisplayMode(.inline)
            .task { await viewModel.loadQueueIfNeeded() }
            .refreshable { await viewModel.loadQueue() }
        }
    }

    /// 翻到背面后卡片会变高（多了释义+词根+例句），评分按钮也跟着冒出来——固定
    /// VStack 用 Spacer 撑开在内容变高时会把上一个/下一个按钮直接挤没（Spacer
    /// 被压到 0 也不够，内容超出屏幕高度后中间这段就没地方待了）。用 ScrollView +
    /// GeometryReader 撑出至少一屏高：内容没塞满屏幕时两个 Spacer 会把卡片顶到
    /// 正中间（跟之前视觉效果一样），内容超出屏幕高度时 Spacer 压到 0，改成正常
    /// 往下滚，不会再被挤没。
    private func cardContent(_ word: VocabularyWord) -> some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: 24) {
                    Text("\(viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)

                    Spacer(minLength: 0)

                    flipCard(word)
                        .padding(.horizontal)

                    // 上一个/下一个只在还没翻卡（回忆阶段）时出现，是给"跳过这个词，
                    // 先去看别的"用的；一旦翻到背面看了释义，就应该老老实实点认识/模糊/
                    // 不认识评分，不能既看了答案又假装没看直接跳走。
                    if !viewModel.isFlipped {
                        HStack(spacing: 16) {
                            navButton("上一个", systemImage: "chevron.left", enabled: viewModel.canGoPrevious) {
                                viewModel.goToPrevious()
                            }
                            navButton("下一个", systemImage: "chevron.right", iconTrailing: true, enabled: viewModel.canGoNext) {
                                viewModel.goToNext()
                                if let next = viewModel.currentWord {
                                    Pronouncer.shared.speak(next.word)
                                }
                            }
                        }
                    }

                    Spacer(minLength: 0)

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
                    }

                    if viewModel.isFlipped {
                        HStack(spacing: 12) {
                            ratingButton("😵 不认识", Theme.unknown, .unknown)
                            ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                            ratingButton("😊 认识", Theme.known, .known)
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 24)
                    }
                }
                .padding(.top, 16)
                .frame(minHeight: geo.size.height)
            }
        }
    }

    /// 卡片翻转用两层叠放 + 各自反向补偿旋转，而不是单层直接转 180°：单层转到
    /// 180° 时背面内容会呈现镜像（左右翻转、文字读不出来）。背面预先转 180°
    /// 抵消一次，外层再转 180° 时正好抵消回正常朝向，静止两端（0°/180°）都是
    /// 正常可读的，只有转动过程中间是"侧面"，看起来才是真的在翻卡片。
    private func flipCard(_ word: VocabularyWord) -> some View {
        ZStack {
            cardFace(word, isBack: false)
                .opacity(viewModel.isFlipped ? 0 : 1)
            cardFace(word, isBack: true)
                .rotation3DEffect(.degrees(180), axis: (x: 0, y: 1, z: 0))
                .opacity(viewModel.isFlipped ? 1 : 0)
        }
        .rotation3DEffect(.degrees(viewModel.isFlipped ? 180 : 0), axis: (x: 0, y: 1, z: 0))
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.4)) { viewModel.flip() }
        }
        // onTapGesture 本身不会被 VoiceOver 当成可激活元素，加上 button 语义 +
        // 明确的 label/hint，双击手势才能触发翻卡片。
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(word.word)
        .accessibilityHint(viewModel.isFlipped ? "已展开释义，双击收起" : "双击查看释义")
    }

    private func cardFace(_ word: VocabularyWord, isBack: Bool) -> some View {
        VStack(spacing: 16) {
            HStack {
                Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                PronounceButton(word: word.word)
            }
            Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)

            if isBack {
                Text("\(word.partOfSpeech) \(word.definitionZh)")
                    .font(.title3)
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)
                    .padding(.top, 8)

                if !word.etymology.isEmpty {
                    Text("词根：\(word.etymology)")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                }
                if !word.exampleSentence.isEmpty {
                    Text(word.exampleSentence)
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                }
            } else {
                Text("点击翻转看释义")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .frame(minHeight: 220)
        .background(Theme.surface)
        .clipShape(.rect(cornerRadius: 16))
    }

    /// 用带方向箭头的胶囊按钮代替之前纯文字的灰色方块——加了图标更有"往哪边翻"
    /// 的方向感，胶囊形状 + 强调色描边/浅色底也更像一个真正可点的控件，而不是
    /// 一块跟卡片背景差不多的灰色矩形。
    private func navButton(
        _ label: String, systemImage: String, iconTrailing: Bool = false,
        enabled: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if !iconTrailing { Image(systemName: systemImage) }
                Text(label)
                if iconTrailing { Image(systemName: systemImage) }
            }
            .font(.subheadline.weight(.semibold))
        }
        .foregroundStyle(enabled ? Theme.accent : Theme.textSecondary.opacity(0.35))
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(enabled ? Theme.accent.opacity(0.12) : Theme.surface)
        .clipShape(.capsule)
        .overlay {
            Capsule().strokeBorder(enabled ? Theme.accent.opacity(0.3) : .clear, lineWidth: 1)
        }
        .buttonStyle(.pressable)
        .disabled(!enabled)
    }

    private func ratingButton(_ label: String, _ color: Color, _ rating: ReviewRating) -> some View {
        Button {
            Task { await viewModel.submit(rating) }
        } label: {
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.2))
                .foregroundStyle(color)
                .clipShape(.rect(cornerRadius: 10))
        }
        .buttonStyle(.pressable)
        .disabled(viewModel.isSubmitting)
    }
}
