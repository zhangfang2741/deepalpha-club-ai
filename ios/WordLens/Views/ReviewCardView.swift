// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @EnvironmentObject var nav: AppNavigationState

    /// 评分后顶部浮出的确认 toast：「✓ 已标记为认识」之类，1.2s 自动消失。
    /// 切下一张卡（currentIndex 推进）也能继续显示——给用户一个明确的"刚才那个动作
    /// 已经被接住"的视觉信号，避免连点三档按钮后回不过神来自己评了什么。
    @State private var confirmationMessage: String?
    @State private var confirmationColor: Color = .clear

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.isFinished {
                    // 评分会即时从队列移除词，评完最后一个 queue 就空了——所以"完成"
                    // 必须在"队列空"之前判断，否则会错显示成"今天没有待复习"。
                    ContentUnavailableView(
                        "今日复习完成 🎉",
                        systemImage: "star.fill",
                        description: Text("共复习了 \(viewModel.reviewedCount) 个单词")
                    )
                } else if viewModel.queue.isEmpty {
                    ContentUnavailableView(
                        "今天没有待复习的单词",
                        systemImage: "checkmark.circle",
                        description: Text("去拍照识别一些新单词吧")
                    )
                } else if let word = viewModel.currentWord {
                    cardContent(word)
                        .id(word.id)
                        .transition(.opacity.combined(with: .scale(scale: 0.96)))
                        // 评分后 currentIndex 常常不变（删掉当前词、后一个顶上来），
                        // 靠 word.id 变化来触发切词动画，比盯 currentIndex 更准。
                        .animation(.spring(response: 0.45, dampingFraction: 0.85),
                                   value: viewModel.currentWord?.id)
                }

                // 顶部确认 toast：放在最外层 ZStack 里、走 own alignment(.top)，
                // 不参与 cardContent 的 transition，切词/翻卡时不会被一起淡掉。
                // safeAreaInset 会让 toast 跟着 navbar/progressBar 一起被挤进
                // navigation chrome，而我们要的是覆盖在内容上的浮层，所以走
                // overlay 而不是 safeAreaInset。
                confirmationToast
                    .padding(.top, 8)
                    .allowsHitTesting(false)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .navigationTitle("")
            // Toolbar-managed title: 用 ToolbarItem(placement: .principal)
            // 自己渲染"首页"文字. NavigationStack 内置的 .navigationTitle
            // 会随 content subtree 的 .id + .transition 重布局, 切词时肉眼
            // 看像 title "闪一下"; 放到 toolbar layer 后, title 由
            // NavigationStack 的 chrome 单独管理, 不跟 cardContent 的
            // transition 一起 fade, 静止不动.
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("首页")
                        .font(.largeTitle.bold())
                        .foregroundStyle(Theme.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        // 学习模式只改队列排序，不动 SM-2 调度；切换即时重排剩余队列。
                        ForEach(ReviewMode.allCases, id: \.self) { m in
                            Button {
                                viewModel.changeMode(m)
                            } label: {
                                if viewModel.mode == m {
                                    Label(m.label, systemImage: "checkmark")
                                } else {
                                    Text(m.label)
                                }
                            }
                        }
                    } label: {
                        Image(systemName: "slider.horizontal.3")
                    }
                    .tint(Theme.accent)
                    .accessibilityLabel("学习模式")
                }
            }
            .task { await viewModel.loadQueueIfNeeded() }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task { await viewModel.loadQueue() }
            }
            .refreshable { await viewModel.loadQueue() }
            // 自动播放 FAB 用 .safeAreaInset 钉在 NavigationStack 底部 ——
            // 之前放在 body ZStack 里 + Theme.background.ignoresSafeArea() 共存时,
            // SwiftUI 在 Prepare build 阶段预渲染 view tree 时, FAB 的
            // .allowsHitTesting(viewModel.currentWord != nil) 让 FAB 跟导航栏
            // 安全区 navigate 同时被纳入 preflight, 触发 "invalid reuse after
            // initialization failure" 崩溃。
            // .safeAreaInset 把 FAB 推到 NavigationStack 的底部工具栏区,
            // 跟主 view tree 完全分离 — preflight 阶段 FAB 不会被
            // 跟 cardContent 的 transition 一起处理, crash 来源被消除。
            .safeAreaInset(edge: .bottom, alignment: .center, spacing: 0) {
                autoplayButton
                    .padding(.bottom, 16)
                    .opacity(viewModel.currentWord != nil ? 1 : 0)
                    .allowsHitTesting(viewModel.currentWord != nil)
                    .background(Color.clear)
            }
            // 进度行也提到 outer 用 safeAreaInset(edge: .top) 钉死——
            // 之前进度行写在 cardContent 内, 跟 .id(word.id) +
            // .transition(.opacity + .scale) 同一条 view tree, 切词时
            // SwiftUI 把它视为"remove 旧卡 + insert 新卡"的一部分一起
            // 过渡, 数字"1/5 → 2/5"那一帧就会跟卡片一起淡入淡出闪一下.
            // 提出来独立成 stable 节点, 切词时只 diff Text 里的数字, 位
            // 置永远不动, 不闪.
            .safeAreaInset(edge: .top, alignment: .center, spacing: 0) {
                progressBar
                    .padding(.vertical, 8)
                    // 没有正在复习的卡片时（加载中/无待复习/已完成）隐藏进度，避免
                    // 显示成 "N/0" 这类无意义数字。
                    .opacity(viewModel.currentWord != nil ? 1 : 0)
            }
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
                // 进度行已经从 cardContent 抽出去, 在 outer 用 safeAreaInset
                // 钉死——这里只剩 flipCard + 上下 Spacer + 底部按钮.
                Spacer(minLength: 0)

                flipCard(word)
                    .padding(.horizontal)
                    // word.id 变化时（首次进入、上一个/下一个、评分切到下一张）
                    // 触发发音——挂在 flipCard 上不参与 outer transition.
                    .task(id: word.id) {
                        guard !viewModel.suppressCardAutoSpeak else { return }
                        Pronouncer.shared.speakIfAutoplayEnabled(word.word)
                    }

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

                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
                        .padding(.bottom, 4)
                }
            }
        }
    }

    /// 进度行：从 cardContent 抽出来作为独立的 outer 节点，通过 safeAreaInset
    /// 钉死位置，不会参与切词 transition，每次 currentIndex / autoplayPassIndex
    /// 变化只 diff 内部 Text 数字，不会有 fade/scale 入场动画，肉眼看就是纯数字
    /// 改变、不闪动。
    private var progressBar: some View {
        HStack(spacing: 8) {
            // 分子 = 已评分数 + 当前在剩余队列里的位置：评过的词已从队列移除，
            // reviewedCount 记着删了几个，加上当前位置就是这张卡在原始队列里的序号。
            Text("\(viewModel.reviewedCount + viewModel.currentIndex + 1) / \(viewModel.totalCount)")
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
            // 1) 立刻震一下——按下瞬间就能感觉到反馈，不用等网络回来。
            // 2) 顶部 toast 提示评分结果，1.2s 自动消失。
            // 3) 异步提交评分（成功后会自动切下一个词）。
            Haptics.rating(rating)
            showConfirmation(label: label, color: color)
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

    /// 弹出顶部 toast：emoji + "已标记为 X"。emoji 是从按钮 label 里抠出来的（按钮
    /// 上是「😊 认识」格式），避免再维护一份 i18n 映射表。Task.sleep 兜底——视图
    /// 卸载时 task 自动取消，confirmationMessage 留着不影响后续显示。
    private func showConfirmation(label: String, color: Color) {
        let stripped = label
            .replacingOccurrences(of: "😵 ", with: "")
            .replacingOccurrences(of: "😐 ", with: "")
            .replacingOccurrences(of: "😊 ", with: "")
        confirmationMessage = "已标记为\(stripped)"
        confirmationColor = color
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1.2))
            if confirmationMessage == "已标记为\(stripped)" {
                confirmationMessage = nil
            }
        }
    }

    private var confirmationToast: some View {
        Group {
            if let message = confirmationMessage {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                    Text(message)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(confirmationColor)
                .clipShape(.capsule)
                .shadow(color: confirmationColor.opacity(0.35), radius: 8, x: 0, y: 3)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.85), value: confirmationMessage)
    }
}
