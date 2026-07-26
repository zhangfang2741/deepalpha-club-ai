// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @EnvironmentObject var nav: AppNavigationState
    @State private var showPronunciationSettings = false

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
                        // 当前词变化时（首次进入、上一个/下一个）按需自动发音；翻卡不改变
                        // word.id，不会重复触发。task(id:) 天然处理"变化即执行"，是自动
                        // 发音的唯一入口，受发音设置里的「自动发音」开关控制。
                        //
                        // 自动播放期间 suppressCardAutoSpeak 会被 ReviewViewModel 置
                        // true——状态机会自己发 3 遍，这次 speak 会跟状态机抢节奏导致
                        // 漏一遍，所以这里跳过。
                        .task(id: word.id) {
                            guard !viewModel.suppressCardAutoSpeak else { return }
                            Pronouncer.shared.speakIfAutoplayEnabled(word.word)
                        }
                }
            }
            .navigationTitle("首页")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                // 自动播放：开启后从当前词连播 3 遍、切下一个词、词间停顿。点
                // "下一个/上一个/评分/停止"任意一个都会中断——避免用户错过评分。
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        if viewModel.isAutoplay {
                            viewModel.stopAutoplay()
                        } else {
                            viewModel.startAutoplay()
                        }
                    } label: {
                        Image(systemName: viewModel.isAutoplay ? "stop.circle.fill" : "play.circle.fill")
                    }
                    .tint(viewModel.isAutoplay ? Theme.unknown : Theme.accent)
                    .accessibilityLabel(viewModel.isAutoplay ? "停止自动播放" : "开始自动播放")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showPronunciationSettings = true
                    } label: {
                        // 用小喇叭+齿轮语义的图标表意「发音设置」；纯图标按钮补 label 对
                        // VoiceOver 友好。
                        Image(systemName: "speaker.wave.2.circle")
                    }
                    .tint(Theme.accent)
                    .accessibilityLabel("发音设置")
                }
            }
            .sheet(isPresented: $showPronunciationSettings) {
                PronunciationSettingsView()
            }
            .task { await viewModel.loadQueueIfNeeded() }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task { await viewModel.loadQueue() }
            }
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

                    // 自动播放时显示"正在读第 N / 3 遍"和"X / Y 个词"，让用户清楚
                    // 当前在哪个节奏上；不自动播放时这段隐藏，不抢视觉重点。
                    if viewModel.isAutoplay {
                        HStack(spacing: 12) {
                            Label {
                                Text("第 \(viewModel.autoplayPassIndex + 1) / 3 遍")
                            } icon: {
                                Image(systemName: "speaker.wave.2.fill")
                            }
                            Text("·")
                            Text("\(viewModel.autoplayWordIndex + 1) / \(viewModel.totalCount)")
                        }
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.accent)
                    }

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
                                // 自动发音统一由外层 .task(id: word.id) 触发（受开关控制），
                                // 这里不再单独调 speak，避免同一次切词重复播放。
                                viewModel.goToNext()
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

    /// 拍照页那个主 CTA 按钮是实色填充 + 白字 + 圆角的视觉重量，复习卡片原先的
    /// "胶囊 + 12% 浅底"看起来太轻、像次要操作，跟"翻到下一个单词"这件事的重要
    /// 程度不匹配——切换单词是复习时最频繁的动作之一，应该跟拍照主按钮一样显眼。
    /// 这里照搬拍照按钮的实色填充 / 圆角 / 字号 / padding，唯一区别是 HStack
    /// 里并排两个时不能用 maxWidth: infinity 让它们填满整行（会把卡片挤窄），所以
    /// 保留自然宽度、外加 .frame(maxWidth: .infinity) 让两个按钮在 HStack 里等宽
    /// 分摊水平空间。
    private func navButton(
        _ label: String, systemImage: String, iconTrailing: Bool = false,
        enabled: Bool, action: @escaping () -> Void
    ) -> some View {
        Button {
            action()
        } label: {
            HStack(spacing: 6) {
                if !iconTrailing { Image(systemName: systemImage) }
                Text(label)
                if iconTrailing { Image(systemName: systemImage) }
            }
            .font(.subheadline.weight(.semibold))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(enabled ? Theme.accent : Theme.accent.opacity(0.35))
            .foregroundStyle(.white)
            .clipShape(.rect(cornerRadius: 12))
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
