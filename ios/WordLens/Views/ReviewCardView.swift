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
    @State private var showPlaylistSheet = false
    /// 顶部标题点开的「当前播放队列」下拉框。
    @State private var showQueueDropdown = false

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
                if showQueueDropdown {
                    queueDropdown
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
            // 学习模式挪到设置页之后，改动发生在别的 tab 上。切回首页时对一下
            // UserDefaults，不一致就按新模式重排剩余队列。
            .onChange(of: nav.selectedTab) { _, newTab in
                guard newTab == .review else { return }
                viewModel.changeMode(ReviewMode.current)
            }
            .refreshable { await viewModel.loadQueue() }
            // 全屏「切换分组」页：只管挑分组（词表纯展示）。要跳到某个具体的词
            // 走顶部标题的播放队列下拉框，两件事分开。
            .fullScreenCover(isPresented: $showPlaylistSheet) {
                NowPlayingView(
                    playlistVM: playlistVM,
                    reviewVM: viewModel,
                    onSelect: { selection, name, playImmediately in
                        Task {
                            await viewModel.switchPlaylist(selection, name: name)
                            if playImmediately { viewModel.autoplay.start() }
                        }
                    }
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
            // 评分 + 播放条钉死在底部：跟卡片彻底分离，卡片正反面高度不一样时
            // 它们也纹丝不动。跟 topBar 是同一个套路。
            .safeAreaInset(edge: .bottom, alignment: .center, spacing: 0) {
                bottomControls
                    .opacity(viewModel.currentWord != nil ? 1 : 0)
                    .allowsHitTesting(viewModel.currentWord != nil)
            }
        }
    }

    /// 底部固定区：翻卡后多出评分三档，播放条常驻在最下面。
    private var bottomControls: some View {
        VStack(spacing: 14) {
            if viewModel.isFlipped {
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
    }

    /// 顶部一行：左边「☰ 分组名」，右边进度。
    ///
    /// 整行走 safeAreaInset 钉死，跟卡片的 .id + .transition 完全分离——切词时
    /// 只 diff 里面的文字，位置不动、不跟着淡入淡出。
    private var topBar: some View {
        HStack(alignment: .center) {
            Button {
                withAnimation(.spring(response: 0.32, dampingFraction: 0.85)) {
                    showQueueDropdown.toggle()
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                    Text(viewModel.selectionName)
                        .font(.title3.bold())
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1)
                }
                .contentShape(.rect)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("当前分组 \(viewModel.selectionName)，展开播放队列")

            Spacer(minLength: 12)

            // 没有正在复习的卡片时（加载中/无待复习/已完成）隐藏进度，避免
            // 显示成 "N/0" 这类无意义数字。
            progressBar
                .opacity(viewModel.currentWord != nil ? 1 : 0)
        }
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 10)
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
                flipCard(word)
                    .padding(.horizontal)
                    // word.id 变化时（首次进入、上一个/下一个、评分切到下一张）
                    // 触发发音——挂在 flipCard 上不参与 outer transition.
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
    // MARK: - 播放队列下拉框

    /// 当前分组的完整队列，点任意一个词从那里开始播。
    ///
    /// 跟「切换分组」页的职责分开：那一页只管挑分组、词表纯展示；这里才是在操作
    /// **当前正在播的队列**，所以点词直接生效（跳过去 + 开播），不需要二次确认。
    private var queueDropdown: some View {
        ZStack(alignment: .top) {
            // 点空白处收起。压在面板下面，所以不会挡住面板自己的点击。
            Color.black.opacity(0.35)
                .ignoresSafeArea()
                .onTapGesture {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                        showQueueDropdown = false
                    }
                }

            VStack(spacing: 0) {
                // 「切换分组」做成实心主题色大按钮：之前是一行淡蓝小字，混在
                // 下拉框的文字里根本注意不到。这是本下拉框里唯一的"去别处"操作，
                // 值得用最重的视觉权重，跟下面一列单词明确分层。
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                        showQueueDropdown = false
                    }
                    showPlaylistSheet = true
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "square.grid.2x2.fill")
                            .font(.headline)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("切换分组")
                                .font(.subheadline.weight(.bold))
                            Text("当前：\(viewModel.selectionName)")
                                .font(.caption2)
                                .opacity(0.85)
                        }
                        Spacer()
                        // 这里的箭头是导航语义（点进去是另一个页面），不是装饰——
                        // 跟之前从列表行、标题旁去掉的那些纯装饰小三角不是一回事。
                        Image(systemName: "chevron.right")
                            .font(.footnote.weight(.bold))
                            .opacity(0.9)
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(Theme.accent)
                    .clipShape(.rect(cornerRadius: 12))
                    .shadow(color: Theme.accent.opacity(0.35), radius: 6, x: 0, y: 3)
                    .contentShape(.rect)
                }
                .buttonStyle(.pressable)
                .padding(.horizontal, 10)
                .padding(.top, 10)
                .padding(.bottom, 4)

                HStack(spacing: 6) {
                    Text("播放队列")
                        .font(.caption.weight(.semibold))
                    Text("·")
                    Text("\(viewModel.queue.count) 个")
                    Spacer()
                    Text("点单词从那里开始播")
                        .font(.caption2)
                }
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)

                Divider().overlay(Theme.border)

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 2) {
                            ForEach(Array(viewModel.queue.enumerated()), id: \.element.id) { index, word in
                                queueRow(word, index: index).id(word.id)
                            }
                        }
                        .padding(.vertical, 6)
                    }
                    // 队列可能有几百个词，展开时先滚到正在播的那个，省得自己找。
                    .onAppear {
                        guard let currentID = viewModel.currentWord?.id else { return }
                        proxy.scrollTo(currentID, anchor: .center)
                    }
                }
                // 上限约半屏：再高就把卡片整个盖住了，下拉框应当还看得见下面的内容。
                .frame(maxHeight: 320)
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

    private func queueRow(_ word: VocabularyWord, index: Int) -> some View {
        let isCurrent = word.id == viewModel.currentWord?.id
        return Button {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                showQueueDropdown = false
            }
            viewModel.jump(to: word, play: true)
        } label: {
            HStack(spacing: 10) {
                Group {
                    if isCurrent {
                        Image(systemName: "speaker.wave.2.fill")
                            .foregroundStyle(Theme.accent)
                            .symbolEffect(.variableColor.iterative, isActive: viewModel.autoplay.isPlaying)
                    } else {
                        Text("\(index + 1)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                .frame(width: 22)

                VStack(alignment: .leading, spacing: 2) {
                    Text(word.word)
                        .font(.subheadline.weight(isCurrent ? .bold : .semibold))
                        .foregroundStyle(isCurrent ? Theme.accent : Theme.textPrimary)
                    Text(word.definitionZh)
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(isCurrent ? Theme.surfaceAlt : Color.clear)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(word.word)，\(word.definitionZh)\(isCurrent ? "，正在播放" : "")")
        .accessibilityHint("双击从这个单词开始播放")
    }

    // MARK: - 播放条

    /// 上一个 / 连播 / 下一个 三件一组，做成播放器那样的一整块控件。
    ///
    /// 之前这三个是散的：上一/下一是两颗胶囊按钮、还会在翻卡后被评分按钮整行
    /// 顶掉，连播键则单独浮在别的地方。合成一条常驻的播放条之后，位置永远固定，
    /// 手指不用每次重新找，跟"这是个播放器"的心智也对得上。
    private var transportBar: some View {
        HStack(spacing: 30) {
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
