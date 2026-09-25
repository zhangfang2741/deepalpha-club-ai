import SwiftUI

/// 分析结果详情页（第二页）。
///
/// 由「条件页」在分析成功后 push 进来。只负责呈现结果：图表 + 形态分析/买卖点。
/// 改条件请返回上一页——条件与结果分离，各自专注一件事。
struct ResultDetailView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    @EnvironmentObject private var orientation: AppOrientation

    @State private var showFullscreenChart = false

    /// 截图与分享按钮共用的预览内容。两条入口合流到同一个 state，
    /// 才能只挂一个 `.sheet` —— 同一层级两个 sheet 在 SwiftUI 里会互相吞掉。
    @State private var previewItem: SharePreviewItem?
    @State private var showShareError = false

    /// 星标状态自己持有一份，不从外面传入——「信号」页气泡跳转和「自选」页跳转
    /// 都会 push 到这同一个 ResultDetailView，没必要为了一个星标按钮把这份状态
    /// 一路从 MainTabView 穿过两条不同的调用链传下来。
    @StateObject private var watchlistVM = WatchlistViewModel()

    var body: some View {
        // 曾经尝试把图表固定在顶部、只让 ResultSegments 的 tab 内容单独滚动
        // （给它 .frame(maxHeight: .infinity)）——真机实测图表+MACD+图层图例
        // 本来就占大半屏，留给 tab 内容的"剩余空间"被挤成一个只有几行高的
        // 小框，体验比之前更差，已撤回。回到整页一个 ScrollView，图表和
        // tab 内容一起自然滚动。
        ScrollViewReader { proxy in
            ScrollView {
                pageContent(isStatic: false) {
                    proxy.scrollTo("result-sections", anchor: .top)
                }
            }
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.background)
        .navigationTitle(navTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { shareButton }
            ToolbarItem(placement: .topBarTrailing) { starButton }
        }
        .task { await watchlistVM.refreshSilently() }
        .onReceive(NotificationCenter.default.publisher(for: .watchlistDidChange)) { _ in
            Task { await watchlistVM.refreshSilently() }
        }
        // 预览已经开着时不再响应截图：用户在预览里截图不该再套一层。
        // 全屏图表也要排除：它是盖在本页上的 fullScreenCover，SwiftUI 不会给呈现方发
        // onDisappear，本页监听仍然活着，会和全屏页的监听同时弹 sheet，撞掉一个。
        .onScreenshot(isEnabled: previewItem == nil && !showFullscreenChart) {
            previewItem = SharePreviewItem(image: $0)
        }
        .sheet(item: $previewItem) { item in
            SharePreviewSheet(image: item.image,
                              text: ShareText.share(analysis: analysis, vm: vm))
        }
        .alert(L("生成分享图失败"), isPresented: $showShareError) {
            Button(L("好"), role: .cancel) {}
        } message: {
            Text(L("请稍后重试。"))
        }
        .fullScreenCover(isPresented: $showFullscreenChart) {
            ChartFullscreenView(analysis: analysis, vm: vm)
                .environmentObject(orientation)
        }
        #if DEBUG && targetEnvironment(simulator)
        .task { await MarketingAutomation.playback(vm: vm) }
        #endif
    }

    private var navTitle: String {
        return "\(vm.symbol.uppercased()) · \(ChanViewModel.freqLabel(vm.freq))"
    }

    /// ScrollView 的完整内容，同时是分享长图的渲染源（PageSnapshot.render）。
    ///
    /// 抽成一个方法让屏幕显示与离屏长图复用同一棵视图树，修饰符与顺序保持
    /// 一致——改这里会同时改变页面显示与分享图，两处永不走样。
    /// 分享长图通过 isStatic 隐藏周期与全屏控件，并将 ResultSegments 的三段内容全部展开。
    private func pageContent(isStatic: Bool, onSectionChange: @escaping () -> Void = {}) -> some View {
        VStack(spacing: 14) {
            ChartSection(analysis: analysis, vm: vm,
                         onFullscreen: openFullscreen, isStatic: isStatic)
                .allowsHitTesting(isStatic || !vm.isLoading)
                .accessibilityHidden(!isStatic && vm.isLoading)
                .overlay {
                    if !isStatic && vm.isLoading {
                        // 覆盖图表而不改变布局高度，保留原图直到新周期加载完成。
                        ZStack {
                            Theme.background.opacity(0.75)
                            ProgressView()
                                .controlSize(.large)
                                .tint(Theme.accent)
                                .accessibilityLabel(L("正在切换周期…"))
                        }
                    }
                }

            ResultSegments(analysis: analysis, isStatic: isStatic, onSelectionChange: onSectionChange)
                .id("result-sections")

            compactDisclaimer
        }
        .padding(.horizontal, Theme.contentHInset)
        .padding(.vertical, Theme.contentVInset)
    }

    /// 打开全屏图表（转屏 + 关呈现动画，逻辑同条件页原实现）。
    private func openFullscreen() {
        orientation.enterLandscape()
        var tx = Transaction()
        tx.disablesAnimations = true
        withTransaction(tx) { showFullscreenChart = true }
    }

    // MARK: - 自选

    private var isStarred: Bool {
        watchlistVM.isStarred(market: vm.market, symbol: vm.symbol.uppercased())
    }

    private var starButton: some View {
        Button {
            let symbol = vm.symbol.uppercased()
            // 有真实名称就存名称，没有则退回代码（后端 name 非空约束）。自选列表
            // 侧再判断 name==代码时不重复显示，见 WatchlistItem.displayName。
            let name = vm.displayName ?? symbol
            Task { await watchlistVM.toggle(market: vm.market, symbol: symbol, name: name) }
        } label: {
            Image(systemName: isStarred ? "star.fill" : "star")
                .foregroundColor(isStarred ? Theme.segment : nil)
        }
        .accessibilityLabel(isStarred ? L("移出自选") : L("加入自选"))
    }

    // MARK: - 分享

    private var shareButton: some View {
        Button(action: share) {
            Image(systemName: "square.and.arrow.up")
        }
        .accessibilityLabel(L("分享分析图"))
        .accessibilityHint(L("生成一张带二维码的分析图并打开预览"))
    }

    /// 分享按钮路径：渲染整页长图（完整内容）→ 拼品牌头与免责条 → 弹预览。
    ///
    /// 与截图入口刻意不同：截图给「用户看到的窗口」（所见即所得），这里给
    /// 「整个页面的内容」——不含导航栏/TabBar，没滚到的部分也在图里。
    /// 长图通过 PageSnapshot 离屏渲染内容视图得到，两者最终走同一个 ShareComposer。
    private func share() {
        guard let shot = PageSnapshot.render(pageContent(isStatic: true)),
              let composed = ShareComposer.compose(screenshot: shot) else {
            // 与截图入口不同，这里是用户主动点的，静默失败等于点了没反应，必须报错
            showShareError = true
            return
        }
        previewItem = SharePreviewItem(image: composed)
    }

    /// 压缩版免责声明。完整版在「我的」页——App Store 要求这个可见，不能删。
    private var compactDisclaimer: some View {
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }
}
