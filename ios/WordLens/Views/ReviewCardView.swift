// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @StateObject private var playlistVM = PlaylistViewModel()
    @EnvironmentObject var nav: AppNavigationState
    @EnvironmentObject var store: StoreManager
    @EnvironmentObject var usage: UsageTracker
    /// 学习额度用尽时弹出的订阅墙。
    @State private var showPaywall = false

    /// 评分后顶部浮出的确认 toast：「✓ 已标记为认识」之类，1.2s 自动消失。
    /// 切下一张卡（currentIndex 推进）也能继续显示——给用户一个明确的"刚才那个动作
    /// 已经被接住"的视觉信号，避免连点三档按钮后回不过神来自己评了什么。
    @State private var confirmationMessage: String?
    @State private var confirmationColor: Color = .clear
    /// 顶部标题点开的「当前播放队列」下拉框。
    /// 顶部小三角展开的分组列表。
    @State private var showGroupDropdown = false
    /// 播放条右侧按钮唤出的「当前播放队列」半屏面板。
    @State private var showQueueSheet = false
    /// 听写判定后轻点结果卡进入详情；返回时仍停留在当前判定阶段。
    @State private var detailWord: VocabularyWord?
    /// 听写输入框的焦点。连播读完 3 遍后自动聚焦，用户不用再点一下。
    @FocusState private var isDictationFieldFocused: Bool
    /// 语音听写：点麦克风说单词，识别结果实时写进 dictationInput，判定沿用打字那套。
    @StateObject private var speech = SpeechRecognizer()

    /// 顶部标题两侧为右上角模式控件预留的空间，保证分组名以屏幕为基准居中。
    private static let headerTitleSideClearance: CGFloat = 96
    /// 分组标题与进度状态之间的层级间距。
    private static let headerStatusSpacing: CGFloat = 14
    /// 单词卡、评分区和播放区共用同一条内容边界。
    private static let contentHorizontalPadding: CGFloat = 16
    /// 播放区在横向拉宽后，按钮和图标同步放大，避免控件显得过于稀疏。
    private static let transportTapSize: CGFloat = 48
    private static let transportIconSize: CGFloat = 24
    private static let transportUtilityIconSize: CGFloat = 20
    private static let playCircleSize: CGFloat = 64
    private static let playIconSize: CGFloat = 26

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.isFinished {
                    // 评分会即时从队列移除词，评完最后一个 queue 就空了——所以"完成"
                    // 必须在"队列空"之前判断，否则会错显示成"这一组没有词"。
                    ContentUnavailableView(
                        viewModel.selection.finishedTitle,
                        systemImage: "star.fill",
                        description: Text(L("共复习了 %lld 个单词", viewModel.reviewedCount))
                    )
                } else if viewModel.queue.isEmpty {
                    // 文案跟着当前播放列表走：「今天没有待复习」和「这个歌单还没有
                    // 单词」是两回事，用同一句会让用户以为哪里出错了。
                    ContentUnavailableView(
                        viewModel.selection.emptyTitle,
                        systemImage: "checkmark.circle",
                        description: Text(viewModel.selection.emptyDescription)
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

                // 当前播放队列的下拉框：点顶部标题展开，盖在卡片上方。
                // 放在同一个 top-aligned ZStack 里，位置紧贴导航栏下沿。
                if showGroupDropdown {
                    groupDropdown
                        .zIndex(20)
                }
            }
            .navigationTitle("")
            // Toolbar-managed title: 用 ToolbarItem(placement: .principal)
            // 自己渲染"首页"文字. NavigationStack 内置的 .navigationTitle
            // 会随 content subtree 的 .id + .transition 重布局, 切词时肉眼
            // 看像 title "闪一下"; 放到 toolbar layer 后, title 由
            // NavigationStack 的 chrome 单独管理, 不跟 cardContent 的
            // transition 一起 fade, 静止不动.
            // 导航栏整个藏掉：现在它已经没有任何内容了，而「☰ 分组名」放进
            // toolbar 会被 iOS 26 的玻璃控件按固定尺寸裁掉文字，只剩一个圆图标。
            // 自己在内容区画这一行，宽度、字号才完全可控。
            .toolbar(.hidden, for: .navigationBar)
            .task { await viewModel.loadQueueIfNeeded() }
            // 接线学习额度闸门：订阅用户直接放行；免费用户按 UsageTracker 判定。
            // 放 .task 里而不是 init，因为 store/usage 是环境对象，且切语言/重建时
            // 需要重新绑定当前实例。
            .task {
                viewModel.autoplay.learningGate = { [store, usage] wordID in
                    store.isSubscribed || usage.canLearn(wordID: wordID)
                }
                viewModel.autoplay.onWordLearned = { [usage] wordID in
                    usage.recordLearned(wordID: wordID)
                }
                viewModel.autoplay.onLearningBlocked = { showPaywall = true }
            }
            .task {
                // 面板里的歌单名要在首屏就能用（标题显示的是当前组的名字，如果当前
                // 组是个自定义歌单，名字只能从歌单列表里查）。
                await playlistVM.load()
                viewModel.selectionName = playlistVM.name(for: viewModel.selection)
            }
            .onChange(of: nav.vocabularyDataVersion) { _, _ in
                Task {
                    await viewModel.loadQueue()
                    await playlistVM.load()
                }
            }
            .onChange(of: nav.selectedTab) { oldTab, newTab in
                guard oldTab == .study, newTab != .study else { return }
                isDictationFieldFocused = false
                showGroupDropdown = false
            }
            .refreshable { await viewModel.loadQueue() }
            // 队列面板：fullScreenCover 只负责盖住 tab bar，系统转场由
            // presentQueue / dismissQueue 关闭；实际的右侧滑入动画由抽屉自身完成。
            .fullScreenCover(isPresented: $showQueueSheet) {
                QueueDrawerView(
                    words: viewModel.queue,
                    currentWordID: viewModel.currentWord?.id,
                    onSelect: { word in
                        dismissQueue()
                        viewModel.jump(to: word, play: true)
                    },
                    onDismiss: dismissQueue
                )
                .presentationBackground(.clear)
                .interactiveDismissDisabled()
            }
            .navigationDestination(item: $detailWord) { word in
                WordDetailView(word: word)
                    // 学习页本身隐藏了导航栏；进入详情后恢复导航栏，提供返回按钮。
                    .toolbar(.visible, for: .navigationBar)
            }
            // 自动播放 FAB 用 .safeAreaInset 钉在 NavigationStack 底部 ——
            // 之前放在 body ZStack 里 + Theme.background.ignoresSafeArea() 共存时,
            // SwiftUI 在 Prepare build 阶段预渲染 view tree 时, FAB 的
            // .allowsHitTesting(viewModel.currentWord != nil) 让 FAB 跟导航栏
            // 安全区 navigate 同时被纳入 preflight, 触发 "invalid reuse after
            // initialization failure" 崩溃。
            // .safeAreaInset 把 FAB 推到 NavigationStack 的底部工具栏区,
            // 跟主 view tree 完全分离 — preflight 阶段 FAB 不会被
            // 跟 cardContent 的 transition 一起处理, crash 来源被消除。
            // 底部不再有任何浮动按钮：连播键已经嵌进 tab bar 正中间（见
            // MainTabView.playButton），分组入口挪到了左上角的 ☰。
            // 进度行也提到 outer 用 safeAreaInset(edge: .top) 钉死——
            // 之前进度行写在 cardContent 内, 跟 .id(word.id) +
            // .transition(.opacity + .scale) 同一条 view tree, 切词时
            // SwiftUI 把它视为"remove 旧卡 + insert 新卡"的一部分一起
            // 过渡, 数字"1/5 → 2/5"那一帧就会跟卡片一起淡入淡出闪一下.
            // 提出来独立成 stable 节点, 切词时只 diff Text 里的数字, 位
            // 置永远不动, 不闪.
            .safeAreaInset(edge: .top, alignment: .center, spacing: 0) {
                topBar
            }
            // 听写模式下连播读完 3 遍会停在这个词等输入，这时自动把键盘唤起来，
            // 用户不用再多点一下输入框。passIndex 走到最后一遍即认为读完。
            .onChange(of: viewModel.autoplay.passIndex) { _, newValue in
                guard viewModel.isDictation, viewModel.dictationPhase.isInput else { return }
                guard newValue == AutoplayController.passCount - 1 else { return }
                isDictationFieldFocused = true
            }
            // 评分 + 播放条钉死在底部：跟卡片彻底分离，卡片正反面高度不一样时
            // 它们也纹丝不动。跟 topBar 是同一个套路。
            .safeAreaInset(edge: .bottom, alignment: .center, spacing: 0) {
                bottomControls
                    .opacity(viewModel.currentWord != nil ? 1 : 0)
                    .allowsHitTesting(viewModel.currentWord != nil)
            }
            .sheet(isPresented: $showPaywall) { PaywallView() }
        }
    }

    /// 底部固定区：
    /// - 只听模式：翻卡后多出评分三档
    /// - 听写模式：等输入时是「确定」，判定后由卡片上的左右滑手势决策
    /// 播放条两种模式下都常驻在最下面。
    private var bottomControls: some View {
        VStack(spacing: 14) {
            if viewModel.isDictation {
                if viewModel.dictationPhase.isInput {
                    confirmDictationButton
                        .padding(.horizontal, Self.contentHorizontalPadding)
                        .transition(.opacity)
                }
            } else if viewModel.isFlipped {
                HStack(spacing: 10) {
                    ratingButton(L("😵 不认识"), Theme.unknown, .unknown)
                    ratingButton(L("😐 模糊"), Theme.fuzzy, .fuzzy)
                    ratingButton(L("😊 认识"), Theme.known, .known)
                }
                .padding(.horizontal, Self.contentHorizontalPadding)
                .transition(.opacity)
            }

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(Theme.unknown)
            }

            transportBar
        }
        // 往上抬一截：贴着 tab bar 时播放键跟系统那排图标挤在一起，既容易误触
        // 也显得整个页面被压到底。
        .padding(.bottom, 72)
        .animation(.easeInOut(duration: 0.2), value: viewModel.isFlipped)
        .animation(.easeInOut(duration: 0.2), value: viewModel.dictationPhase)
    }

    /// 听写的「确定」：空输入禁止提交。
    ///
    /// 「空输入等于不认识」原来也是设计上的一种可能——但用户习惯性点完才发现
    /// 自己被判成不认识，体验不友好：让它必须显式打点什么才算提交，听写语义才
    /// 站得住（"我至少要试着拼一下"）。
    ///
    /// 键盘回车（TextField.onSubmit）也走同样的判断。
    private var confirmDictationButton: some View {
        let canSubmit = !viewModel.dictationInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !viewModel.isSubmitting
        return Button(action: confirmDictation) {
            Text(L("确定"))
                .font(.subheadline.weight(.bold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(canSubmit ? Theme.accent : Theme.surface)
                .foregroundStyle(canSubmit ? .white : Theme.textSecondary.opacity(0.5))
                .clipShape(.rect(cornerRadius: 12))
                .overlay {
                    RoundedRectangle(cornerRadius: 12).strokeBorder(
                        canSubmit ? .clear : Theme.border, lineWidth: 1
                    )
                }
        }
        .buttonStyle(.pressable)
        .disabled(!canSubmit)
    }

    private func confirmDictation() {
        let typed = viewModel.dictationInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !typed.isEmpty, !viewModel.isSubmitting else { return }
        isDictationFieldFocused = false
        viewModel.submitDictation()
    }

    private func acceptDictationResult() {
        guard viewModel.isAwaitingDictationDecision else { return }
        confirmationMessage = nil
        isDictationFieldFocused = false
        Task {
            _ = await viewModel.acceptDictationResult()
        }
    }

    private func retryDictation() {
        confirmationMessage = nil
        viewModel.retryDictation()
        // phase 切回 .input 后 TextField 要到下一轮视图更新才存在，yield 一帧再聚焦。
        Task { @MainActor in
            await Task.yield()
            guard viewModel.isDictation, viewModel.dictationPhase.isInput else { return }
            isDictationFieldFocused = true
        }
    }

    /// 顶部固定区：右侧是「只听/听写」开关，正中是分组名和它下面的播放进度。
    ///
    /// 整行走 safeAreaInset 钉死，跟卡片的 .id + .transition 完全分离——切词时
    /// 只 diff 里面的文字，位置不动、不跟着淡入淡出。
    private var topBar: some View {
        VStack(spacing: 0) {
            // 第一层只负责标题和模式选择，让两者共享一条稳定的垂直基线。
            ZStack(alignment: .center) {
                Button {
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.85)) {
                        showGroupDropdown.toggle()
                    }
                } label: {
                    HStack(spacing: 4) {
                        Text(viewModel.selectionName)
                            .font(.title3.bold())
                            .foregroundStyle(Theme.textPrimary)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Theme.accent)
                            .rotationEffect(.degrees(showGroupDropdown ? 180 : 0))
                    }
                    .padding(.horizontal, 8)
                    .frame(minHeight: 44)
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(L("当前分组 %@，展开分组列表", viewModel.selectionName))
                .padding(.horizontal, Self.headerTitleSideClearance)

                HStack {
                    Spacer()
                    studyModeToggle
                }
            }

            // 第二层是独立状态胶囊。和标题拉开距离后，不会再挤在标题基线上。
            // 没有卡片时直接移除，避免出现 "N/0" 这类无意义数字。
            if viewModel.currentWord != nil {
                // 队列进度是"这一组还剩几个"，额度是"今天还能学几个新词"，两件事
                // 都影响用户接下来怎么安排，默认并排放在同一条基线上。
                //
                // 用 ViewThatFits 而不是直接 HStack：播放时进度胶囊会变长
                // （多出「第 1 / 3 遍」），窄机型上两个胶囊并排会挤到文字截断。
                // 放不下就自动竖排，任何屏宽都不会出现 "今日新..." 这种半截文案。
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        progressBar
                        FreeQuotaBadge(kind: .word, style: .compact) { showPaywall = true }
                    }
                    VStack(spacing: 6) {
                        progressBar
                        FreeQuotaBadge(kind: .word, style: .compact) { showPaywall = true }
                    }
                }
                .padding(.top, Self.headerStatusSpacing)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 14)
    }

    /// 右上角的学习方式分段器：视觉上保持紧凑，但每个选项仍有 44pt 点击区域。
    private var studyModeToggle: some View {
        HStack(spacing: 0) {
            ForEach(StudyMode.allCases, id: \.self) { mode in
                let isSelected = viewModel.studyMode == mode
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        viewModel.changeStudyMode(to: mode)
                    }
                } label: {
                    Text(mode.label)
                        .font(.caption.bold())
                        .foregroundStyle(isSelected ? .white : Theme.textSecondary)
                        .frame(width: 44, height: 44)
                        .background {
                            Capsule()
                                .fill(isSelected ? Theme.accent : .clear)
                                .frame(width: 40, height: 28)
                        }
                        .contentShape(.rect)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(mode.label)
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
        .frame(height: 44)
        .background {
            Capsule()
                .fill(Theme.surface)
                .frame(height: 32)
        }
        .overlay {
            Capsule()
                .strokeBorder(Theme.border, lineWidth: 1)
                .frame(height: 32)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(L("学习方式"))
    }

    /// 卡片区：只剩卡片本身，垂直居中。
    ///
    /// 评分按钮和播放条都搬到了 outer 的 safeAreaInset(edge: .bottom)——它们
    /// 原先跟卡片同在一个 VStack 里，卡片一高一矮（正面只有单词、背面还有释义
    /// 词根例句）整排按钮就跟着上下窜。
    ///
    /// 用 GeometryReader 撑一个 minHeight 而不是直接去掉 ScrollView：短内容时
    /// `alignment: .center` 把卡片顶到正中间，长内容（释义/例句很长）超过一屏
    /// 时又还能滚动，两头都不塌。
    private func cardContent(_ word: VocabularyWord) -> some View {
        GeometryReader { geo in
            ScrollView {
                Group {
                    // 听写模式不走翻卡——正面本来就没东西可藏，翻卡在这里没有意义。
                    if viewModel.isDictation {
                        dictationCard(word)
                    } else {
                        flipCard(word)
                    }
                }
                .padding(.horizontal, Self.contentHorizontalPadding)
                // word.id 变化时（首次进入、上一个/下一个、评分切到下一张）
                // 触发发音——挂在卡片上不参与 outer transition.
                .task(id: word.id) {
                    guard nav.selectedTab == .study else { return }
                    guard !viewModel.suppressCardAutoSpeak else { return }
                    Pronouncer.shared.speakIfAutoplayEnabled(word.word)
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: geo.size.height, alignment: .center)
            }
            // 结果卡等待左右决策时，锁住父级纵向滚动。否则卡片虽然只设置了 x
            // 偏移，手指的 y 分量仍会驱动 ScrollView，看起来像卡片还能上下移动。
            .scrollDisabled(viewModel.isAwaitingDictationDecision)
        }
    }

    /// 进度行：从 cardContent 抽出来作为独立的 outer 节点，通过 safeAreaInset
    /// 钉死位置，不会参与切词 transition，每次 currentIndex / passIndex
    /// 变化只 diff 内部 Text 数字，不会有 fade/scale 入场动画，肉眼看就是纯数字
    /// 改变、不闪动。
    private var progressBar: some View {
        let current = viewModel.reviewedCount + viewModel.currentIndex + 1
        return HStack(spacing: 8) {
            // 分子 = 已评分数 + 当前在剩余队列里的位置：评过的词已从队列移除，
            // reviewedCount 记着删了几个，加上当前位置就是这张卡在原始队列里的序号。
            Text("\(current) / \(viewModel.totalCount)")
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.textSecondary)
            if viewModel.autoplay.isPlaying {
                Divider()
                    .frame(height: 12)
                Label {
                    Text(
                        viewModel.autoplay.isReadingExample
                            ? L("正在读例句")
                            : L("第 %lld / %lld 遍", viewModel.autoplay.passIndex + 1, AutoplayController.passCount)
                    )
                } icon: {
                    Image(systemName: viewModel.autoplay.isReadingExample
                          ? "quote.bubble.fill" : "speaker.wave.2.fill")
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.accent)
            }
        }
        .monospacedDigit()
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Theme.surface)
        .clipShape(.capsule)
        .overlay {
            Capsule().strokeBorder(Theme.border, lineWidth: 1)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(L("学习进度"))
        .accessibilityValue(progressAccessibilityValue)
    }

    private var progressAccessibilityValue: String {
        let current = viewModel.reviewedCount + viewModel.currentIndex + 1
        let progress = L("第 %lld 个，共 %lld 个", current, viewModel.totalCount)
        guard viewModel.autoplay.isPlaying else { return progress }
        if viewModel.autoplay.isReadingExample {
            return L("%@，正在朗读英文例句", progress)
        }
        return L("%@，正在播放第 %lld 遍，共 %lld 遍",
                 progress, viewModel.autoplay.passIndex + 1, AutoplayController.passCount)
    }

    /// 自动播放按钮：圆 + 图标 + 阴影，包在 Button 里复用 .pressable 样式
    /// （按压有缩放反馈，跟评分按钮手感一致）。之前的 drag 逻辑整段移除——
    /// 浮动 + 长按拖动的定位在滑动列表里 coordinateSpace 容易错乱，用户反馈
    /// "拖动一下乱跑"，干脆不做浮动、不写位置，固定放在卡片下方居中。
    // MARK: - 分组下拉框

    /// 顶部小三角展开的分组列表：点一个分组直接切过去并开始播。
    ///
    /// 换组以前要「点 ☰ → 点切换分组 → 进全屏页 → 点分组」四步，现在一步到位。
    /// 这里也不再有二次确认——点具体分组本身就是明确的意图表达。
    private var groupDropdown: some View {
        ZStack(alignment: .top) {
            // 点空白处收起。压在面板下面，不会挡住面板自己的点击。
            Color.black.opacity(0.35)
                .ignoresSafeArea()
                .onTapGesture { closeGroupDropdown() }

            VStack(spacing: 0) {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        // “待复习”是按 next_review_at 动态计算的跨状态队列，不是
                        // “不认识 / 模糊 / 认识”的父级总数，单独放在系统根节点下，
                        // 避免用户把它误解成下面三个状态数量之和。
                        GroupSectionHeader(
                            title: L("系统复习"),
                            systemImage: "calendar.badge.clock"
                        )
                        groupRow(.dueReview, label: L("待复习"), dot: nil)

                        GroupSectionHeader(
                            title: L("生词库分组"),
                            systemImage: "tray.full.fill",
                            separatesPreviousSection: true
                        )
                        ForEach(statusGroups, id: \.selection) { group in
                            groupRow(group.selection, label: group.label, dot: group.dot)
                        }

                        GroupSectionHeader(
                            title: L("自定义"),
                            systemImage: "folder.fill",
                            separatesPreviousSection: true
                        )
                        if customGroups.isEmpty {
                            Text(L("还没有自定义分组，去「生词库 › 分组管理」新建"))
                                .font(.caption)
                                .foregroundStyle(Theme.textSecondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.leading, 24)
                                .padding(.trailing, 16)
                                .padding(.vertical, 10)
                        } else {
                            ForEach(customGroups, id: \.selection) { group in
                                groupRow(group.selection, label: group.label, dot: group.dot)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                }
                .frame(maxHeight: 380)
            }
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 14))
            .overlay {
                RoundedRectangle(cornerRadius: 14).strokeBorder(Theme.border, lineWidth: 1)
            }
            .shadow(color: .black.opacity(0.35), radius: 16, x: 0, y: 8)
            .padding(.horizontal, 12)
            .transition(.move(edge: .top).combined(with: .opacity))
        }
    }

    private func closeGroupDropdown() {
        withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
            showGroupDropdown = false
        }
    }

    private var statusGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        [
            (.status("new"), L("不认识"), Theme.unknown),
            (.status("fuzzy"), L("模糊"), Theme.fuzzy),
            (.status("known"), L("认识"), Theme.known),
        ]
    }

    private var customGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        playlistVM.playlists.map { (.custom($0.id), $0.name, nil) }
    }

    private func groupRow(
        _ selection: PlaylistSelection, label: String, dot: Color?
    ) -> some View {
        let isCurrent = selection == viewModel.selection
        let count = playlistVM.count(for: selection)
        return Button {
            closeGroupDropdown()
            guard !isCurrent else { return }
            Task {
                await viewModel.switchPlaylist(selection, name: label)
                // 点具体分组 = 想听这一组，直接开播，不用再找播放键。
                viewModel.autoplay.start()
            }
        } label: {
            HStack(spacing: 10) {
                if let dot {
                    Circle().fill(dot).frame(width: 7, height: 7)
                } else {
                    Circle().fill(.clear).frame(width: 7, height: 7)
                }
                Text(label)
                    .font(.subheadline.weight(isCurrent ? .bold : .regular))
                    .foregroundStyle(isCurrent ? Theme.accent : Theme.textPrimary)
                Spacer()
                Text("\(count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
                if isCurrent {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.caption2)
                        .foregroundStyle(Theme.accent)
                }
            }
            .padding(.leading, 24)
            .padding(.trailing, 16)
            .padding(.vertical, 11)
            .background(isCurrent ? Theme.surfaceAlt : Color.clear)
            .contentShape(.rect)
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(L("%@，%lld 个%@", label, count, isCurrent ? L("，当前分组") : ""))
    }

    /// 播放条最左：播放顺序（对应 ReviewMode），跟播放器上「循环/随机」那颗键
    /// 同一个位置、同一个语义——当场改变"接下来按什么顺序过词"。
    ///
    /// 用 Menu 而不是点一下循环到下一档：有四档，盲切完还得低头确认落在哪个，
    /// 不如直接摊开选。图标跟着当前档位变，不展开也能看出现在是哪种顺序。
    private var playOrderButton: some View {
        Menu {
            ForEach(ReviewMode.allCases, id: \.self) { mode in
                Button {
                    viewModel.changeMode(mode)
                } label: {
                    if viewModel.mode == mode {
                        Label(mode.label, systemImage: "checkmark")
                    } else {
                        Text(mode.label)
                    }
                }
            }
        } label: {
            ReviewModeIcon(mode: viewModel.mode)
                // 按钮始终展示“当前生效的播放模式”，四种模式应使用相同的激活色。
                .foregroundStyle(Theme.accent)
                .frame(width: Self.transportTapSize, height: Self.transportTapSize)
                .contentShape(.rect)
        }
        .accessibilityLabel(L("播放顺序，当前%@", viewModel.mode.label))
    }

    /// 播放条最右：看当前分组的完整队列。
    private var queueButton: some View {
        Button(action: presentQueue) {
            Image(systemName: "list.bullet")
                .font(.system(size: Self.transportUtilityIconSize, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: Self.transportTapSize, height: Self.transportTapSize)
                .contentShape(.rect)
        }
        .buttonStyle(.pressable)
        .disabled(viewModel.queue.isEmpty || viewModel.isAwaitingDictationDecision)
        .accessibilityLabel(L("播放队列"))
    }

    private func presentQueue() {
        // 播放队列与分组下拉框是互斥的覆盖层。先立即收起分组，避免队列从右侧
        // 滑入后下拉框仍留在底层，并在关闭队列时重新露出来。
        isDictationFieldFocused = false
        showGroupDropdown = false
        // 再无系统动画地挂载全屏容器；抽屉会在下一帧从右侧滑入。
        setQueuePresented(true)
    }

    private func dismissQueue() {
        setQueuePresented(false)
    }

    private func setQueuePresented(_ isPresented: Bool) {
        var transaction = Transaction()
        transaction.disablesAnimations = true
        withTransaction(transaction) {
            showQueueSheet = isPresented
        }
    }

    // MARK: - 播放条

    /// 上一个 / 连播 / 下一个 三件一组，做成播放器那样的一整块控件。
    ///
    /// 之前这三个是散的：上一/下一是两颗胶囊按钮、还会在翻卡后被评分按钮整行
    /// 顶掉，连播键则单独浮在别的地方。合成一条常驻的播放条之后，位置永远固定，
    /// 手指不用每次重新找，跟"这是个播放器"的心智也对得上。
    private var transportBar: some View {
        HStack(spacing: 0) {
            playOrderButton
            Spacer(minLength: 8)

            transportButton(
                "backward.end.fill",
                label: L("上一个"),
                enabled: viewModel.canGoPrevious && !viewModel.isAwaitingDictationDecision
            ) {
                viewModel.goToPrevious()
            }
            Spacer(minLength: 8)

            playCircle
            Spacer(minLength: 8)

            transportButton(
                "forward.end.fill",
                label: L("下一个"),
                enabled: viewModel.canGoNext && !viewModel.isAwaitingDictationDecision
            ) {
                viewModel.goToNext()
            }
            Spacer(minLength: 8)

            queueButton
        }
        // 不加面板底色：这一条就浮在页面背景上，跟卡片各自独立。加了毛玻璃面板
        // 反而在深色背景上糊成一块灰，抢卡片的视觉重量。
        .frame(maxWidth: .infinity)
        .padding(.horizontal, Self.contentHorizontalPadding)
        .padding(.vertical, 4)
    }

    /// 中间的连播键：圆底衬一层浅色，播放中换成暂停图标并填成主题色。
    private var playCircle: some View {
        let isPlaying = viewModel.autoplay.isPlaying
        return Button {
            viewModel.autoplay.toggle()
        } label: {
            Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: Self.playIconSize, weight: .bold))
                .foregroundStyle(isPlaying ? .white : Theme.textPrimary)
                .frame(width: Self.playCircleSize, height: Self.playCircleSize)
                .background(
                    Circle().fill(isPlaying ? Theme.accent : Color.white.opacity(0.14))
                )
                .shadow(color: isPlaying ? Theme.accent.opacity(0.4) : .clear, radius: 8, x: 0, y: 3)
        }
        .buttonStyle(.pressable)
        .disabled(viewModel.queue.isEmpty)
        .accessibilityLabel(isPlaying ? L("暂停连播") : L("开始连播"))
    }

    private func transportButton(
        _ systemImage: String, label: String, enabled: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: Self.transportIconSize, weight: .medium))
                .foregroundStyle(enabled ? Theme.textPrimary : Theme.textSecondary.opacity(0.4))
                // 图标本身远小于 44pt，撑开点按区域到最小可点尺寸。
                .frame(width: Self.transportTapSize, height: Self.transportTapSize)
                .contentShape(.rect)
        }
        .buttonStyle(.pressable)
        .disabled(!enabled)
        .accessibilityLabel(label)
    }

    // MARK: - 听写卡片

    /// 听写模式的卡片：等输入时它**就是**填写框，判定后翻出答案。
    @ViewBuilder
    private func dictationCard(_ word: VocabularyWord) -> some View {
        switch viewModel.dictationPhase {
        case .input:
            dictationInputCard
        case .revealed(let answered, let typed, let rating):
            DictationResultCard(
                word: answered,
                typed: typed,
                resultLabel: Self.dictationResultLabel(rating),
                resultColor: Self.ratingColor(rating),
                showsTypedInput: rating != .known,
                isSubmitting: viewModel.isSubmitting,
                onOpenDetail: { detailWord = answered },
                onAccept: acceptDictationResult,
                onRetry: retryDictation
            )
        }
    }

    private var dictationInputCard: some View {
        VStack(spacing: 18) {
            Label(L("听音写词"), systemImage: "speaker.wave.2.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.textSecondary)

            HStack(spacing: 0) {
                // 左侧留一块和麦克风等宽的透明占位，输入的词才是真正居中的。
                Color.clear.frame(width: 44, height: 44)

                TextField("", text: $viewModel.dictationInput)
                    .textFieldStyle(.plain)
                    .font(.title.bold())
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.textPrimary)
                    // 这四个必须全关：只要系统插手自动大写/纠错/联想，它会替用户把词
                    // 拼对，听写就白做了。
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .keyboardType(.asciiCapable)
                    .submitLabel(.done)
                    .focused($isDictationFieldFocused)
                    .onSubmit { confirmDictation() }
                    .padding(.vertical, 10)

                voiceDictationButton
            }
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(Theme.accent.opacity(0.6))
                    .frame(height: 2)
            }
            .padding(.horizontal, 24)

            voiceDictationHint

            Text(L("打字，或点麦克风逐个字母拼读（A-P-P-L-E），写完点「确定」或敲回车"))
                .font(.caption2)
                .multilineTextAlignment(.center)
                .foregroundStyle(Theme.textSecondary.opacity(0.8))
        }
        .padding()
        .frame(maxWidth: .infinity)
        .frame(minHeight: 220)
        .background(Theme.surface)
        .clipShape(.rect(cornerRadius: 16))
        // 点卡片空白处也能唤起键盘，不用非得戳中那一行输入框。
        .contentShape(.rect)
        .onTapGesture { isDictationFieldFocused = true }
        // 识别到的文字先过一遍拼读还原（A-P-P-L-E → apple），再写进听写输入框，
        // 后续确认/判定完全复用打字那套。
        .onChange(of: speech.transcript) { _, text in
            let parsed = SpellingParser.parse(text)
            guard !parsed.isEmpty else { return }
            viewModel.dictationInput = parsed
        }
        // 相位切到「已判定」或卡片消失时，确保麦克风关掉、音频会话还给发音。
        .onChange(of: viewModel.dictationPhase) { _, phase in
            if !phase.isInput { speech.stop() }
        }
        .onDisappear { speech.stop() }
    }

    /// 麦克风按钮：贴在输入框右侧，点一下开始听，说完再点一下停（拿到 final 结果
    /// 也会自动停）。录音时先收起键盘，避免键盘挡住卡片、也避免抢焦点。
    private var voiceDictationButton: some View {
        Button {
            if speech.isListening {
                speech.stop()
            } else {
                isDictationFieldFocused = false
                // 再点一次就是「重说一遍」：先清空上一次的结果，免得这次没识别出
                // 东西时框里还留着上一遍的词。
                viewModel.dictationInput = ""
                Task { await speech.start() }
            }
        } label: {
            Image(systemName: speech.isListening ? "waveform.circle.fill" : "mic.circle.fill")
                .font(.system(size: 26))
                .foregroundStyle(speech.isListening ? Theme.unknown : Theme.accent)
                .symbolEffect(.variableColor.iterative, isActive: speech.isListening)
                // 图标只有 26pt，但点击热区仍撑满 44×44 的最小可点面积。
                .frame(width: 44, height: 44)
                .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(speech.isListening ? L("停止语音听写") : L("开始语音听写"))
    }

    /// 麦克风的状态提示（报错优先）。
    @ViewBuilder
    private var voiceDictationHint: some View {
        if let error = speech.errorMessage {
            VStack(spacing: 4) {
                Text(error)
                    .font(.caption2)
                    .foregroundStyle(Theme.unknown)
                    .multilineTextAlignment(.center)

                // 权限被拒后系统不会再弹授权框，在 App 里怎么点麦克风都没反应。
                // 必须给一条通往系统设置的明路，否则用户只能自己去翻设置，
                // 或者以为功能坏了。受限（屏幕使用时间等）跳过去也没有开关，
                // 所以那种情况不显示这个按钮。
                if speech.permissionBlocker?.isFixableInSettings == true {
                    Button(L("去设置")) {
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            UIApplication.shared.open(url)
                        }
                    }
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Theme.accent)
                }
            }
        } else if speech.isListening {
            Text(L("正在听，一个字母一个字母地念…"))
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
        }
    }

    private static func ratingColor(_ rating: ReviewRating) -> Color {
        switch rating {
        case .known: return Theme.known
        case .fuzzy: return Theme.fuzzy
        case .unknown: return Theme.unknown
        }
    }

    private static func ratingLabel(_ rating: ReviewRating) -> String {
        switch rating {
        case .known: return L("认识")
        case .fuzzy: return L("模糊")
        case .unknown: return L("不认识")
        }
    }

    private static func dictationResultLabel(_ rating: ReviewRating) -> String {
        switch rating {
        case .known: return L("记住了")
        case .fuzzy: return L("模糊")
        case .unknown: return L("没记住")
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
        .accessibilityHint(viewModel.isFlipped ? L("已展开释义，双击收起") : L("双击查看释义"))
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
                    Text(L("词根：%@", word.etymology))
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
                Text(L("点击翻转看释义"))
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
                // 三档按钮等宽，英文（如「😵 Don't know」）比中文长，限定单行并允许
                // 缩放，避免其中一个换行变高、三个按钮高度参差。
                .lineLimit(1)
                .minimumScaleFactor(0.7)
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
        showToast(L("已标记为%@", stripped), color: color)
    }

    private func showToast(_ message: String, color: Color) {
        confirmationMessage = message
        confirmationColor = color
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1.2))
            if confirmationMessage == message {
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
