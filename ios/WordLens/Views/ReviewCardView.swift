// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @EnvironmentObject var nav: AppNavigationState

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
                        // word.id 变化时（首次进入、上一个/下一个、评分切到下一张）触发
                        // .task 发音；自动播放期间让状态机自己发 3 遍，这里跳过避免抢
                        // 节奏。task(id:) 的"变化即执行"正好对应卡片内容切换的瞬间，
                        // 视觉上的滑入动画和听感上的发音可以同步出现。
                        .task(id: word.id) {
                            guard !viewModel.suppressCardAutoSpeak else { return }
                            Pronouncer.shared.speakIfAutoplayEnabled(word.word)
                        }
                        // 切词动画：旧卡按 transitionDirection 方向滑出，新卡从对侧滑入。
                        // .id(word.id) 是关键——没有 id 时 SwiftUI 会复用 view hierarchy，
                        // transition 不触发。transitionDirection 在 goTo/submit 那一瞬
                        // 间就被 set 好，渲染这一刻读到的值就是这一笔的出/入方向。
                        .id(word.id)
                        .transition(.asymmetric(
                            insertion: viewModel.transitionDirection >= 0
                                ? .move(edge: .trailing).combined(with: .opacity)
                                : .move(edge: .leading).combined(with: .opacity),
                            removal:   viewModel.transitionDirection >= 0
                                ? .move(edge: .leading).combined(with: .opacity)
                                : .move(edge: .trailing).combined(with: .opacity)
                        ))
                        .animation(.spring(response: 0.45, dampingFraction: 0.85),
                                   value: viewModel.currentIndex)
                }
            }
            .navigationTitle("首页")
            .task { await viewModel.loadQueueIfNeeded() }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task { await viewModel.loadQueue() }
            }
            .refreshable { await viewModel.loadQueue() }
        }
    }

    /// 布局要点：
    /// 1. 卡片居中（ScrollView 让短/长内容都不会挤出按钮）；
    /// 2. 卡片下方一行紧凑胶囊：回忆阶段是「‹ 上一」+「下一个 ›」，自然宽度
    ///    居中、左右各留空白；翻卡后整行替换成三档评分按钮；
    /// 3. 自动播放按钮单独一行（64pt 圆形），放在所有动作按钮下方居中——
    ///    不再浮动、不拖动，位置永远稳定，不会跟任何按钮撞车；
    /// 4. 进度条（X/Y + 第 N/3 遍）始终在卡片上方，跟 FAB 不抢位置。
    private func cardContent(_ word: VocabularyWord) -> some View {
        ScrollView {
            VStack(spacing: 20) {
                // 进度行：始终显示「X / Y」，自动播放时再追加「第 N / 3 遍」
                HStack(spacing: 8) {
                    Text("\(viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.textSecondary)

                    if viewModel.isAutoplay {
                        Text("·")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(Theme.textSecondary)
                        HStack(spacing: 4) {
                            Image(systemName: "speaker.wave.2.fill")
                                .font(.caption2)
                            Text("第 \(viewModel.autoplayPassIndex + 1) / 3 遍")
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                    }
                }
                .padding(.top, 8)

                Spacer(minLength: 0)

                flipCard(word)
                    .padding(.horizontal)

                Spacer(minLength: 24)

                // 底部动作条：回忆阶段是上一/下一（紧凑胶囊，自然宽度，
                // 居中），翻卡后是评分三档；两者都用 HStack 但不带
                // .frame(maxWidth: .infinity)，避免拉满整行的"占满感"。
                if !viewModel.isFlipped {
                    HStack(spacing: 12) {
                        prevNextButton("上一个", systemImage: "chevron.left",
                                       enabled: viewModel.canGoPrevious) {
                            viewModel.goToPrevious()
                        }
                        prevNextButton("下一个", systemImage: "chevron.right",
                                       iconTrailing: true,
                                       enabled: viewModel.canGoNext) {
                            viewModel.goToNext()
                        }
                    }
                    .padding(.bottom, 4)
                } else {
                    HStack(spacing: 10) {
                        ratingButton("😵 不认识", Theme.unknown, .unknown)
                        ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                        ratingButton("😊 认识", Theme.known, .known)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 4)
                }

                // 自动播放大按钮：64pt 圆形，居中。颜色随播放状态切换——
                // 停止时主题色 + 播放图标，播放中红色 + 停止图标，远距离也能
                // 识别当前状态。
                autoplayButton

                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
                        .padding(.bottom, 4)
                }
            }
        }
    }

    /// 自动播放按钮：圆 + 图标 + 阴影，包在 Button 里复用 .pressable 样式
    /// （按压有缩放反馈，跟评分按钮手感一致）。之前的 drag 逻辑整段移除——
    /// 浮动 + 长按拖动的定位在滑动列表里 coordinateSpace 容易错乱，用户反馈
    /// "拖动一下乱跑"，干脆不做浮动、不写位置，固定放在卡片下方居中。
    private var autoplayButton: some View {
        Button {
            if viewModel.isAutoplay {
                viewModel.stopAutoplay()
            } else {
                viewModel.startAutoplay()
            }
        } label: {
            Image(systemName: viewModel.isAutoplay ? "stop.fill" : "play.fill")
                .font(.title2.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 64, height: 64)
                .background(
                    Circle().fill(viewModel.isAutoplay ? Theme.unknown : Theme.accent)
                )
                .shadow(color: (viewModel.isAutoplay ? Theme.unknown : Theme.accent).opacity(0.4),
                        radius: 8, x: 0, y: 4)
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(viewModel.isAutoplay ? "停止自动播放" : "开始自动播放")
        .accessibilityAddTraits(.isButton)
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

    /// 紧凑胶囊按钮：上一/下一自然宽度（按内容自适应），不再 .frame(maxWidth:
    /// .infinity) 拉满整行——之前的"实色填充 + 拉满"看着像表单提交按钮，跟卡片
    /// 视觉重量不平衡、也显得"占满"。胶囊 + 半透明主题色底 + 加粗字重更有
    /// "控件"的克制感。padding 比评分按钮大一圈，因为切词是复习最高频的操作。
    private func prevNextButton(
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
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(enabled ? Theme.accent.opacity(0.15) : Theme.surface)
            .foregroundStyle(enabled ? Theme.accent : Theme.textSecondary.opacity(0.5))
            .clipShape(.capsule)
            .overlay {
                Capsule().strokeBorder(
                    enabled ? Theme.accent.opacity(0.3) : .clear,
                    lineWidth: 1
                )
            }
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
