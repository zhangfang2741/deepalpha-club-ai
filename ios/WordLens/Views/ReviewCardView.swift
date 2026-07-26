// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()
    @EnvironmentObject var nav: AppNavigationState
    @State private var showPronunciationSettings = false

    /// 自动播放 FAB 的位置偏移（pt）。默认值 bottom=20、trailing=20 是 iOS FAB
    /// 通用位置，但实际用起来 FAB 会压在评分按钮上——用户拖一次就能挪开，位
    /// 置会存到 UserDefaults，下次进来直接恢复。
    @State private var fabOffsetX: CGFloat = 20
    @State private var fabOffsetY: CGFloat = 140
    /// 拖动期间留个临时的"正在拖"标志，用来抑制 onTap 误触发（按下后手指移
    /// 动会被 DragGesture 消费，但有时 SwiftUI 会先发一次 tap 再识别 drag）。
    @State private var fabIsDragging = false

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
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                // toolbar 上只留发音设置——自动播放按钮改到卡片右下角做浮动大按钮，
                // 那里视觉重量更足、单手握持时拇指也更容易够到。
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showPronunciationSettings = true
                    } label: {
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
            // 进入页面时读出之前用户拖到的位置。
            .onAppear { restoreFabPosition() }
        }
    }

    /// UserDefaults key 和读写逻辑：x/y 分开存，方便 default 值独立更新而不
    /// 影响老用户（直接存 CGPoint 的 Data 解析麻烦，且老数据迁移风险大）。
    private enum FabPositionStore {
        static let xKey = "review_fab_offset_x"
        static let yKey = "review_fab_offset_y"

        static func load() -> (x: CGFloat, y: CGFloat) {
            let x = UserDefaults.standard.object(forKey: xKey) as? CGFloat
            let y = UserDefaults.standard.object(forKey: yKey) as? CGFloat
            return (x ?? 20, y ?? 140)
        }

        static func save(x: CGFloat, y: CGFloat) {
            UserDefaults.standard.set(x, forKey: xKey)
            UserDefaults.standard.set(y, forKey: yKey)
        }
    }

    private func restoreFabPosition() {
        let pos = FabPositionStore.load()
        fabOffsetX = pos.x
        fabOffsetY = pos.y
    }

    /// 布局要点：
    /// 1. 卡片居中（GeometryReader + ScrollView 让短/长内容都不会挤没按钮）；
    /// 2. 卡片下方一行紧凑胶囊：回忆阶段是「‹ 上一」+「下一个 ›」，自然宽度
    ///    居中、左右各留空白；翻卡后整行替换成三档评分按钮；
    /// 3. 自动播放按钮做成卡片右下角的圆形 FAB（64pt），跟卡片有视觉层级——
    ///    播放中是红色 + 停止图标，停止时是主题色 + 播放图标，64pt 比 toolbar
    ///    的 22pt 图标大一倍多、单手拇指更容易够到；
    /// 4. 进度条（X/Y + 第 N/3 遍）始终在卡片上方，跟 FAB 不抢位置。
    private func cardContent(_ word: VocabularyWord) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .bottom) {
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
                            .padding(.bottom, 8)
                        } else {
                            HStack(spacing: 10) {
                                ratingButton("😵 不认识", Theme.unknown, .unknown)
                                ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                                ratingButton("😊 认识", Theme.known, .known)
                            }
                            .padding(.horizontal)
                            .padding(.bottom, 8)
                        }

                        if let errorMessage = viewModel.errorMessage {
                            Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
                                .padding(.bottom, 4)
                        }
                    }
                    .frame(minHeight: geo.size.height)
                }

                // 浮动播放按钮（FAB）：默认右下角偏上（offsetX=20, offsetY=140），
                // 比之前直接贴角的位置高出一截，不会和"认识"按钮撞在一起。
                // 用户可以长按拖到任意位置，位置存到 UserDefaults，下次恢复。
                //
                // simultaneousGesture 而不是 .gesture：FAB 自身已经挂了 .onTapGesture
                // 处理单击，drag 必须和它同时收到事件才能不被 tap 吞掉。
                autoplayFAB
                    .offset(x: -fabOffsetX, y: -fabOffsetY)
                    .simultaneousGesture(fabDragGesture(in: geo.size))
                    .animation(fabIsDragging ? nil : .spring(response: 0.3, dampingFraction: 0.8),
                               value: fabOffsetX)
                    .animation(fabIsDragging ? nil : .spring(response: 0.3, dampingFraction: 0.8),
                               value: fabOffsetY)
            }
        }
    }

    /// FAB 拖动手势：每次 onChanged 累加 translation。10pt 位移阈值用来区分
    /// tap / drag——onChanged 一旦累计位移 >= 10pt 就置 fabIsDragging=true
    /// （fabTapSurface 里的 onTapGesture 会忽略这次的 tap 候选），onEnded
    /// 再根据 fabIsDragging 决定落盘还是完全回滚。
    ///
    /// 安全区：FAB 不能拖到屏幕外（要保证 64pt 圆形至少有 32pt 在屏幕内），
    /// 也不能盖住卡片顶部的进度文字——顶部留 80pt 不让进，底部要预留 80pt 给
    /// 评分/上一下一按钮的命中区域。
    private func fabDragGesture(in containerSize: CGSize) -> some Gesture {
        let fabSize: CGFloat = 64
        let safeInsets = fabSize / 2 + 8   // FAB 中心至少离边 8pt
        let topReserve: CGFloat = 80         // 顶部进度条不让进
        let bottomReserve: CGFloat = 80      // 底部按钮不让进
        let dragActivationDistance: CGFloat = 10

        // 记录本次手势的"起点 offset"和"是否被判定为 drag"——这两个值在
        // onChanged/onEnded 之间需要跨闭包共享，用本地 closure 捕获（不是
        // @State 字段，避免和 SwiftUI view diffing 干扰）。
        var startX: CGFloat = 0
        var startY: CGFloat = 0
        var activatedDrag = false

        return DragGesture(minimumDistance: 0)
            .onChanged { value in
                if !activatedDrag {
                    let dx = value.translation.width
                    let dy = value.translation.height
                    if hypot(dx, dy) < dragActivationDistance {
                        // 位移太小，保留 tap 候选，不动 offset、不置 fabIsDragging
                        return
                    }
                    // 第一次越过阈值：锁定起点，进入 drag 模式
                    activatedDrag = true
                    startX = fabOffsetX
                    startY = fabOffsetY
                    fabIsDragging = true
                }
                let proposedX = startX - value.translation.width
                let proposedY = startY - value.translation.height
                let centerX = containerSize.width - proposedX
                let centerY = containerSize.height - proposedY
                let minX = safeInsets
                let maxX = containerSize.width - safeInsets
                let minY = topReserve
                let maxY = containerSize.height - bottomReserve
                let clampedX = min(max(centerX, minX), maxX)
                let clampedY = min(max(centerY, minY), maxY)
                fabOffsetX = containerSize.width - clampedX
                fabOffsetY = containerSize.height - clampedY
            }
            .onEnded { _ in
                if activatedDrag {
                    fabIsDragging = false
                    FabPositionStore.save(x: fabOffsetX, y: fabOffsetY)
                }
                activatedDrag = false
            }
    }

    /// 浮动播放按钮：64pt 圆形，跟卡片有阴影分层。颜色随播放状态切换：停止时
    /// 用主题色 + 播放图标，播放中用红色 + 停止图标，让用户远距离也能识别当前
    /// 状态。
    ///
    /// 点击/拖动的判定：用 `.onTapGesture` + `.simultaneousGesture(DragGesture)`
    /// 自己分流——之前的 Button + .gesture(DragGesture) 写法 Button 会吞掉所有
    /// 事件、drag.onChanged 根本收不到；改用 onTapGesture + simultaneousGesture
    /// 后两者都能拿到事件，再用「手指累计位移 < 10pt → 算 tap」的阈值判定。
    /// 视觉效果保持不变（按压 scale + 阴影），行为上单击/拖动都灵敏。
    private var autoplayFAB: some View {
        fabTapSurface
    }

    /// FAB 视觉主体：圆形 + 图标 + 阴影。点击和拖动的事件都在外层包装。
    private var fabVisual: some View {
        Image(systemName: viewModel.isAutoplay ? "stop.fill" : "play.fill")
            .font(.title2.weight(.bold))
            .foregroundStyle(.white)
            .frame(width: 64, height: 64)
            .background(
                Circle().fill(viewModel.isAutoplay ? Theme.unknown : Theme.accent)
            )
            .shadow(color: (viewModel.isAutoplay ? Theme.unknown : Theme.accent).opacity(0.4),
                    radius: 8, x: 0, y: 4)
            .scaleEffect(fabIsDragging ? 1.08 : 1.0)
            .animation(.spring(response: 0.25, dampingFraction: 0.6), value: fabIsDragging)
    }

    /// 把"点击区域"和"视觉主体"合并的容器层——所有手势都挂在这里而不是内层，
    /// 这样 64pt 圆形整体都是可点击 / 可拖动区域，不会被圆形视觉边界限制。
    private var fabTapSurface: some View {
        fabVisual
            .contentShape(.rect)
            .onTapGesture {
                // 拖动中的 tap 是误触，忽略掉
                guard !fabIsDragging else { return }
                if viewModel.isAutoplay {
                    viewModel.stopAutoplay()
                } else {
                    viewModel.startAutoplay()
                }
            }
            .accessibilityLabel(viewModel.isAutoplay ? "停止自动播放" : "开始自动播放")
            .accessibilityHint("长按拖动调整位置")
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