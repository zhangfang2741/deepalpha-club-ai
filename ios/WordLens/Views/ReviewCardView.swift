// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @StateObject private var playlistVM = PlaylistViewModel()
    @EnvironmentObject var nav: AppNavigationState

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
    /// 听写输入框的焦点。连播读完 3 遍后自动聚焦，用户不用再点一下。
    @FocusState private var isDictationFieldFocused: Bool

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
                        description: Text("共复习了 \(viewModel.reviewedCount) 个单词")
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
            .refreshable { await viewModel.loadQueue() }
            // 队列面板：自实现"从右侧滑出"的全高抽屉。
            // 用 fullScreenCover 而不是 .sheet：iOS 26 的 sheet 在长列表里向下滑
            // 会被系统识别成"关闭抽屉"——翻队列时一滑动整个面板就没了。绕开
            // 系统 sheet 的关闭手势，让 ScrollView 自己吃滚动事件，关面板只能用
            // 点遮罩或点关闭按钮（关闭按钮在最顶部、跟工具栏放在一起）。
            .fullScreenCover(isPresented: $showQueueSheet) {
                QueueDrawerView(
                    words: viewModel.queue,
                    currentWordID: viewModel.currentWord?.id,
                    onSelect: { word in
                        showQueueSheet = false
                        viewModel.jump(to: word, play: true)
                    },
                    onDismiss: { showQueueSheet = false },
                    // 抽屉打开前强制收键盘：上一轮自动聚焦让 TextField 成了 first
                    // responder，fullScreenCover 不会自动 dismissKeyboard，键盘就
                    // 一直挂着、在列表里滑动时还能感觉到软键盘在响应。
                    onAppear: { isDictationFieldFocused = false }
                )
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
            // 判定结果用既有的顶部 toast 浮一下。
            .onChange(of: viewModel.dictationPhase) { _, phase in
                guard let rating = phase.rating else { return }
                showConfirmation(
                    label: Self.ratingLabel(rating),
                    color: Self.ratingColor(rating)
                )
            }
            // 评分 + 播放条钉死在底部：跟卡片彻底分离，卡片正反面高度不一样时
            // 它们也纹丝不动。跟 topBar 是同一个套路。
            .safeAreaInset(edge: .bottom, alignment: .center, spacing: 0) {
                bottomControls
                    .opacity(viewModel.currentWord != nil ? 1 : 0)
                    .allowsHitTesting(viewModel.currentWord != nil)
            }
        }
    }

    /// 底部固定区：
    /// - 只听模式：翻卡后多出评分三档
    /// - 听写模式：等输入时是「确定」，判定后什么都不出（自动前进）
    /// 播放条两种模式下都常驻在最下面。
    private var bottomControls: some View {
        VStack(spacing: 14) {
            if viewModel.isDictation {
                if viewModel.dictationPhase.isInput {
                    confirmDictationButton
                        .padding(.horizontal)
                        .transition(.opacity)
                }
            } else if viewModel.isFlipped {
                HStack(spacing: 10) {
                    ratingButton("😵 不认识", Theme.unknown, .unknown)
                    ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                    ratingButton("😊 认识", Theme.known, .known)
                }
                .padding(.horizontal)
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
        return Button {
            isDictationFieldFocused = false
            Task { await viewModel.submitDictation() }
        } label: {
            Text("确定")
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

    /// 顶部固定区：右侧是「只听/听写」开关，正中是分组名和它下面的播放进度。
    ///
    /// 整行走 safeAreaInset 钉死，跟卡片的 .id + .transition 完全分离——切词时
    /// 只 diff 里面的文字，位置不动、不跟着淡入淡出。
    private var topBar: some View {
        ZStack(alignment: .center) {
            // 分组名和播放信息组成居中的两行；左右预留空间，长分组名不会压到开关。
            VStack(spacing: 2) {
                // 顶部分组选择器：居中、放小三角标记可展开。整块可点，三角跟着
                // 展开状态转 180°。
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
                    .padding(.vertical, 2)
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("当前分组 \(viewModel.selectionName)，展开分组列表")
                .padding(.horizontal, 108)

                // 没有正在复习的卡片时（加载中/无待复习/已完成）隐藏进度，避免
                // 显示成 "N/0" 这类无意义数字。
                if viewModel.currentWord != nil {
                    progressBar
                }
            }
            .frame(maxWidth: .infinity)

            HStack {
                Spacer()
                studyModeToggle
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 10)
    }

    /// 右上角的学习方式分段器：两个选项始终可见，当前项用主题色填充。
    /// 比把两个小图标塞进拨片更直观，也能直接点目标模式，不需要猜开关方向。
    private var studyModeToggle: some View {
        HStack(spacing: 2) {
            ForEach(StudyMode.allCases, id: \.self) { mode in
                let isSelected = viewModel.studyMode == mode
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        viewModel.changeStudyMode(to: mode)
                    }
                } label: {
                    Text(mode.label)
                        .font(.subheadline.bold())
                        .foregroundStyle(isSelected ? .white : Theme.textSecondary)
                        .padding(.horizontal, 8)
                        .frame(minHeight: 34)
                        .background(
                            Capsule().fill(isSelected ? Theme.accent : .clear)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel(mode.label)
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
        .padding(3)
        .frame(minHeight: 44)
        .background(Theme.surface)
        .clipShape(.capsule)
        .overlay {
            Capsule().strokeBorder(Theme.border, lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("学习方式")
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
                .padding(.horizontal)
                // word.id 变化时（首次进入、上一个/下一个、评分切到下一张）
                // 触发发音——挂在卡片上不参与 outer transition.
                .task(id: word.id) {
                    guard !viewModel.suppressCardAutoSpeak else { return }
                    Pronouncer.shared.speakIfAutoplayEnabled(word.word)
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: geo.size.height, alignment: .center)
            }
        }
    }

    /// 进度行：从 cardContent 抽出来作为独立的 outer 节点，通过 safeAreaInset
    /// 钉死位置，不会参与切词 transition，每次 currentIndex / passIndex
    /// 变化只 diff 内部 Text 数字，不会有 fade/scale 入场动画，肉眼看就是纯数字
    /// 改变、不闪动。
    private var progressBar: some View {
        HStack(spacing: 8) {
            // 分子 = 已评分数 + 当前在剩余队列里的位置：评过的词已从队列移除，
            // reviewedCount 记着删了几个，加上当前位置就是这张卡在原始队列里的序号。
            Text("\(viewModel.reviewedCount + viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.textSecondary)
            if viewModel.autoplay.isPlaying {
                Text("·")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Theme.textSecondary)
                HStack(spacing: 4) {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.caption2)
                    Text("第 \(viewModel.autoplay.passIndex + 1) / \(AutoplayController.passCount) 遍")
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
                        groupSectionHeader("生词库分组")
                        ForEach(builtinGroups, id: \.selection) { group in
                            groupRow(group.selection, label: group.label, dot: group.dot)
                        }

                        groupSectionHeader("自定义")
                        if customGroups.isEmpty {
                            Text("还没有自定义分组，去「生词库 › 分组管理」新建")
                                .font(.caption)
                                .foregroundStyle(Theme.textSecondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 16)
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

    private var builtinGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        [
            (.dueReview, "待复习", nil),
            (.status("new"), "不认识", Theme.unknown),
            (.status("fuzzy"), "模糊", Theme.fuzzy),
            (.status("known"), "认识", Theme.known),
        ]
    }

    private var customGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        playlistVM.playlists.map { (.custom($0.id), $0.name, nil) }
    }

    private func groupSectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(Theme.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 4)
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
            .padding(.horizontal, 16)
            .padding(.vertical, 11)
            .background(isCurrent ? Theme.surfaceAlt : Color.clear)
            .contentShape(.rect)
        }
        .buttonStyle(.pressable)
        .accessibilityLabel("\(label)，\(count) 个\(isCurrent ? "，当前分组" : "")")
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
            Image(systemName: viewModel.mode.systemImage)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(viewModel.mode == .smart ? Theme.textSecondary : Theme.accent)
                .frame(width: 44, height: 44)
                .contentShape(.rect)
        }
        .accessibilityLabel("播放顺序，当前\(viewModel.mode.label)")
    }

    /// 播放条最右：看当前分组的完整队列。
    private var queueButton: some View {
        Button {
            showQueueSheet = true
        } label: {
            Image(systemName: "list.bullet")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 44, height: 44)
                .contentShape(.rect)
        }
        .buttonStyle(.pressable)
        .disabled(viewModel.queue.isEmpty)
        .accessibilityLabel("播放队列")
    }

    // MARK: - 播放条

    /// 上一个 / 连播 / 下一个 三件一组，做成播放器那样的一整块控件。
    ///
    /// 之前这三个是散的：上一/下一是两颗胶囊按钮、还会在翻卡后被评分按钮整行
    /// 顶掉，连播键则单独浮在别的地方。合成一条常驻的播放条之后，位置永远固定，
    /// 手指不用每次重新找，跟"这是个播放器"的心智也对得上。
    private var transportBar: some View {
        HStack(spacing: 18) {
            playOrderButton

            transportButton(
                "backward.end.fill",
                label: "上一个",
                enabled: viewModel.canGoPrevious
            ) {
                viewModel.goToPrevious()
            }

            playCircle

            transportButton(
                "forward.end.fill",
                label: "下一个",
                enabled: viewModel.canGoNext
            ) {
                viewModel.goToNext()
            }

            queueButton
        }
        // 不加面板底色：这一条就浮在页面背景上，跟卡片各自独立。加了毛玻璃面板
        // 反而在深色背景上糊成一块灰，抢卡片的视觉重量。
        .padding(.vertical, 4)
    }

    /// 中间的连播键：圆底衬一层浅色，播放中换成暂停图标并填成主题色。
    private var playCircle: some View {
        let isPlaying = viewModel.autoplay.isPlaying
        return Button {
            viewModel.autoplay.toggle()
        } label: {
            Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(isPlaying ? .white : Theme.textPrimary)
                .frame(width: 58, height: 58)
                .background(
                    Circle().fill(isPlaying ? Theme.accent : Color.white.opacity(0.14))
                )
                .shadow(color: isPlaying ? Theme.accent.opacity(0.4) : .clear, radius: 8, x: 0, y: 3)
        }
        .buttonStyle(.pressable)
        .disabled(viewModel.queue.isEmpty)
        .accessibilityLabel(isPlaying ? "暂停连播" : "开始连播")
    }

    private func transportButton(
        _ systemImage: String, label: String, enabled: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(enabled ? Theme.textPrimary : Theme.textSecondary.opacity(0.4))
                // 图标本身远小于 44pt，撑开点按区域到最小可点尺寸。
                .frame(width: 44, height: 44)
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
            // 用相位里快照下来的词和输入，而不是 currentWord / dictationInput：
            // 提交评分会让队列前进，读实时值会闪出下一个词的拼写。
            dictationRevealCard(answered, typed: typed, rating: rating)
        }
    }

    private var dictationInputCard: some View {
        VStack(spacing: 18) {
            Label("听音写词", systemImage: "speaker.wave.2.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.textSecondary)

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
                .onSubmit { Task { await viewModel.submitDictation() } }
                .padding(.vertical, 10)
                .overlay(alignment: .bottom) {
                    Rectangle()
                        .fill(Theme.accent.opacity(0.6))
                        .frame(height: 2)
                }
                .padding(.horizontal, 24)

            Text("写完点下面的「确定」，或键盘上敲回车")
                .font(.caption2)
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
    }

    private func dictationRevealCard(
        _ word: VocabularyWord, typed: String, rating: ReviewRating
    ) -> some View {
        let color = Self.ratingColor(rating)
        return VStack(spacing: 14) {
            HStack {
                Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                PronounceButton(word: word.word)
            }
            Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)

            // 写对了就不必再把用户写的重复一遍；写错才需要对照着看差在哪。
            if rating != .known {
                Text("你写的：\(typed.trimmingCharacters(in: .whitespaces).isEmpty ? "（没写）" : typed)")
                    .font(.subheadline)
                    .foregroundStyle(color)
            }

            Text("\(word.partOfSpeech) \(word.definitionZh)")
                .font(.title3)
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity)
        .frame(minHeight: 220)
        .background(Theme.surface)
        .clipShape(.rect(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16).strokeBorder(color.opacity(0.7), lineWidth: 2)
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
        case .known: return "认识"
        case .fuzzy: return "模糊"
        case .unknown: return "不认识"
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
