import SwiftUI

/// 信号雷达 Tab —— 扫描各市场指数成分股跑缠论，把每天在场的买卖点用气泡呈现。只陈列事实、不打分：
/// 后端给的是选中日在场的全部信号（按出现时间从新到旧），不再截取「前 10」。
///
/// 自上而下一条线：顶部 MarketHeader「环境 / 行业 / 当日信号」三格 → 扇区雷达 → 气泡。
/// 三格、扇区标签点开是底部面板（RadarPanels：环境 / 行业 / 当日信号列表）；点气泡、或面板列表里的某一行，
/// 都直接进缠论详情页（不再先弹「大盘 / 行业 / 结构 / 基本面」四层事实页）。
///
/// 扇区雷达（这一天有行业统计时，即美股指数雷达）：角度 = 行业，按当日相对大盘强弱从上往下排，
/// 越靠上越强；每个行业最多画几个最新的气泡，其余在扇区标签上显示「+N」（SectorRadarLayout）。
/// 没有行业统计（港股 / A 股 / 自选）时退回同心环雷达，最多画 ringFieldCap 个最新的，其余点「当日信号」看。
///
/// 气泡编码（三个视觉维度对应三件不同的事，不再互相重复；纯实色气泡，
/// 已确认的左上角打勾、不用边框虚实，见 RadarBubble）：
/// - 颜色：方向（红=买点 / 绿=卖点）+ 深浅（信号强弱：弱/中/强，与详情页买卖点
///   色块同一映射 SignalFormatting.strengthDepth），越强越深；
/// - 大小：买卖点类型（一类最小、二类居中、三类最大——一类只是背驰迹象、尚待验证，
///   三类回踩完全不回中枢，确认程度最高）；
/// - 居中程度：时间距离——当天信号离中心最近，越早出现的信号越靠外；
///   后端会让一只股票的信号在被更新的信号覆盖前持续「在场」（见
///   app/services/signal_radar/service.py 的按日重建），所以翻看某一天时，
///   有的气泡是当天新出现的（右上角标"新"），有的是更早出现、一直有效到今天的。
/// 底部可横滑的日期轨手动选某一天，看当天信号。
/// 点气泡或面板列表里的某一行才跑分析、在本页自己的 NavigationStack 里 push 到缠论分析详情页——
/// 不经过分析 Tab 的条件页中转，右滑手势/返回按钮也就自然直接回到信号页。
struct SignalRadarView: View {
    /// 与分析 Tab 共享的缠论状态（同 MorningReportTabView），这样从信号页
    /// 分析过的标的，切到分析 Tab 时条件与结果也是同步的。
    @ObservedObject var chanVM: ChanViewModel

    @StateObject private var vm = SignalRadarViewModel()
    /// 叠在雷达左上角的指数切换按钮实测尺寸，气泡摆位时避开（见 fieldObstacles）。
    /// 气泡摆位缓存（见 FieldLayoutCache）。
    @State private var layoutCache = FieldLayoutCache()
    @StateObject private var panicVM = PanicIndexViewModel()
    @StateObject private var overviewVM = MarketOverviewViewModel()
    @EnvironmentObject private var orientation: AppOrientation
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    /// 信号雷达图跟会员完全是同一套 UI（同一个 vm），未订阅时唯一的区别：
    /// vm.days 最前面多一天「上个月 1 号」的真实快照（见 SignalRadarViewModel.demoDay），
    /// 默认停在这天；点日期轨上其它天会弹这个付费墙，而不是真的切过去——见 selectDay。
    @State private var showPaywall = false
    /// 免责声明：第一次查看非示例日的雷达图（即订阅会员后的真实雷达）时弹出，
    /// 同意前该日的气泡不显示；示例日（未订阅的免费预览）不弹。见 needsConsent。
    @StateObject private var consent = RadarConsent()
    @State private var consentChecked = false
    @State private var showConsent = false
    /// 强制最短阅读时长（秒）：勾选框可以随时点，但「同意并继续」在这段时间内
    /// 保持禁用——避免手快的用户没看内容就秒点同意，让确认更站得住脚。
    static let consentMinReadSeconds = 10
    @State private var consentSecondsRemaining = SignalRadarView.consentMinReadSeconds

    /// 日期轨直接摆出来的格子数（约 2 周的交易日），更早的走"更多"里的日期选择器。
    static let visibleDayChipCount = 10

    /// 分析成功后置 true，push 到详情页；返回（含右滑手势）时自动复位。
    @State private var showResults = false
    /// 日期轨"更多"打开的日期选择器状态。
    @State private var showDatePicker = false
    @State private var pickedDate = Date()
    /// 图例旁「算法说明」问号按钮打开的详细说明弹层状态。
    @State private var showAlgorithmInfo = false
    /// 正在打开的底部面板（环境 / 行业 / 当日信号 / 某个气泡的四层事实）。
    @State private var panel: RadarPanel?
    /// 面板列表里点了某一行：等面板收起后再跑分析、push 详情页（见 sheet 的 onDismiss）。
    @State private var pendingDetail: RadarSignal?
    /// 雷达上方并列的 tab：缠论买卖点 / 基本面研究（评级升降）。分析师评级等接口数据备齐后再并进来。
    enum RadarTab: String, CaseIterable, Identifiable {
        case chan, fundamental
        var id: String { rawValue }
        var title: String { self == .chan ? L("缠论") : L("基本面研究") }
    }
    @State private var radarTab: RadarTab = .chan
    @StateObject private var gradeVM = GradeEventsViewModel()
    /// 基本面 tab 里「另有 N 个 · 查看全部」打开的半屏。
    @State private var showGradeAll = false

    var body: some View {
        NavigationStack {
            radarContent
            .background(Theme.background)
            .navigationTitle(L("市场雷达"))
            .navigationBarTitleDisplayMode(.inline)
            // 真实滚动窗口雷达对所有用户都拉（未订阅一样看得到市场卡片、图例、日期轨，
            // 跟会员一模一样，见 radarContent）；市场切换时 .task(id:) 额外拉一次
            // 「上个月 1 号」免费预览快照，自动取消上一次未完成的请求、重新拉一次。
            .task { vm.onAppear() }
            // 后台补算未完成时定期静默重拉，补上的成分股不用用户手动刷新就能出现；
            // 离开页面时 SwiftUI 自动取消，补算完成后 refreshWhileBackfilling 直接返回、不发请求。
            .task {
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: SignalRadarViewModel.backfillPollSeconds * 1_000_000_000)
                    await vm.refreshWhileBackfilling()
                }
            }
            .task(id: vm.demoKey) {
                if !store.isPremium { await vm.loadDemoDay() }
            }
            // 行业强弱跟着所选日走：雷达翻到哪天，扇区就按哪天收盘的强弱排
            .task(id: vm.sectorBoardKey) { await vm.loadSectorBoardIfNeeded() }
            // 切到基本面 tab、或在 tab 里换市场 / 指数时拉评级升降
            .task(id: "\(radarTab.rawValue)|\(vm.market.rawValue)|\(vm.activeUniverseKey)|\(store.isPremium)") {
                if radarTab == .fundamental, store.isPremium {
                    await gradeVM.load(market: vm.market.rawValue, universe: vm.activeUniverseKey)
                }
            }
            .sheet(item: $panel, onDismiss: {
                guard let s = pendingDetail else { return }
                pendingDetail = nil
                openSymbol(s.symbol, name: s.name)
            }) { panel in
                panelView(panel)
            }
            // 订阅层级同步进 vm（跟 ChanViewModel.hasSubLevelAccess 同一个模式，vm 本身
            // 不感知 StoreKit）。initial: true 保证首次进入就同步一次，不用等 tier 变化。
            // 降级/过期（如 StoreKit 交易更新把 tier 打回免费档）时若还没拉过免费预览，
            // 补拉一次——上面 `.task(id: vm.demoKey)` 只在市场/指数切换时触发，没切就不会
            // 自动去拉，不补的话会一直停在真实滚动窗口里点不开的那些天。
            .onChange(of: store.isPremium, initial: true) { _, isPremium in
                vm.isPremiumUser = isPremium
                if !isPremium && vm.demoDay == nil {
                    Task { await vm.loadDemoDay() }
                }
            }
            .overlay { if chanVM.isLoading { analysisLoadingOverlay } }
            .navigationDestination(isPresented: $showResults) {
                if let analysis = chanVM.analysis {
                    ResultDetailView(analysis: analysis, vm: chanVM)
                        .environmentObject(orientation)
                }
            }
            .alert(chanVM.errorMessage ?? "", isPresented: Binding(
                get: { !showResults && chanVM.errorMessage != nil },
                set: { if !$0 { chanVM.errorMessage = nil } }
            )) {
                Button(L("好"), role: .cancel) {}
            }
            .sheet(isPresented: $showPaywall) { PaywallView() }
            // 免责声明：要看非示例日的真实雷达、且还没同意过时弹出（含订阅刚生效、
            // 从示例日切到真实日期的那一刻）。可下滑关闭，关闭后气泡区保持锁定并给入口重开。
            .sheet(isPresented: $showConsent) { consentView }
            .onChange(of: needsConsent, initial: true) { _, needs in
                if needs { showConsent = true }
            }
        }
    }

    /// 当前选中的是非示例日、且还没同意过免责声明。示例日（vm.unlockedDayDate，仅未订阅
    /// 时存在）不需要；会员没有示例日，所有日期都需要。
    private var needsConsent: Bool {
        guard !consent.hasAgreed, let day = vm.selectedDay else { return false }
        return day.date != vm.unlockedDayDate
    }

    /// 正文：市场卡片 + 雷达。跟会员完全同一套 UI，未订阅时唯一的区别在 vm.days
    /// （最前面多一天免费预览）和 selectDay（点非解锁日弹付费墙）。非示例日未同意免责
    /// 声明时，气泡区换成锁定占位（consentLockedField）。
    private var radarContent: some View {
        VStack(spacing: 12) {
            MarketHeader(radarVM: vm, panicVM: panicVM, overviewVM: overviewVM) { p in
                // 行业 / 当日信号面板列的是选中日的真实信号，与气泡同一道免责声明门槛；环境不涉及个股
                if needsConsent && p != .environment {
                    showConsent = true
                } else {
                    panel = p
                }
            }

            tabPicker

            if radarTab == .fundamental {
                fundamentalContent
            } else if vm.isScanning {
                scanningView
            } else if vm.isComputingInBackground {
                computingView
            } else if let error = vm.errorMessage {
                errorView(error)
            } else if vm.days.isEmpty {
                emptyView
            } else {
                metaRow
                if needsConsent {
                    consentLockedField
                } else {
                    bubbleField
                        // 同一市场/指数重新加载时保留旧气泡、调暗，期间暂不响应点按；不再盖转圈，
                        // 加载提示只有「正在扫描」一种（切市场/指数走 scanningView）
                        .opacity(vm.isReloading ? 0.35 : 1)
                        .allowsHitTesting(!vm.isReloading)
                        .animation(.easeInOut(duration: 0.2), value: vm.isReloading)
                }
                legend
                dateRail
                Spacer(minLength: 0)
                compactDisclaimer
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    // MARK: - 并列 tab

    /// 下划线式 tab（文字 + 选中项下方一条蓝线），和上面行业胶囊、日期格子的圆角块样式区分开。
    private var tabPicker: some View {
        HStack(spacing: 28) {
            ForEach(RadarTab.allCases) { tab in
                let selected = tab == radarTab
                Button { radarTab = tab } label: {
                    VStack(spacing: 5) {
                        Text(tab.title)
                            .font(.system(size: 16, weight: selected ? .bold : .regular))
                            .foregroundColor(selected ? Theme.textPrimary : Theme.textSecondary)
                        Capsule()
                            .fill(selected ? Theme.accent : Color.clear)
                            .frame(height: 3)
                    }
                    .fixedSize()
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 4)
    }

    /// 基本面研究 tab：会员功能（与缠论雷达真实数据同一道门槛，未订阅点按弹付费墙），同样要先同意免责声明。
    @ViewBuilder
    private var fundamentalContent: some View {
        if !store.isPremium {
            VStack(spacing: 12) {
                Image(systemName: "lock.fill").font(.system(size: 28)).foregroundColor(Theme.textSecondary)
                Text(L("订阅后可查看股票池每天的综合评级升降"))
                    .font(.footnote).foregroundColor(Theme.textSecondary).multilineTextAlignment(.center)
                Button(L("查看订阅")) { showPaywall = true }.buttonStyle(.bordered).tint(Theme.accent)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if !consent.hasAgreed {
            consentLockedField
        } else {
            GradeEventsView(vm: gradeVM, universeName: currentUniverseName, sectorName: { vm.sectorName($0) },
                            showAll: $showGradeAll,
                            onOpen: { symbol, name in openSymbol(symbol, name: name) }) {
                bubbleField
            }
        }
    }

    // MARK: - 免责声明

    /// 气泡区锁定占位：非示例日、未同意免责声明时代替气泡显示，可重新打开声明。
    private var consentLockedField: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 30)).foregroundColor(Theme.textSecondary)
            Text(L("查看市场雷达前，请阅读并同意免责声明"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button(L("阅读免责声明")) { showConsent = true }
                .buttonStyle(.bordered).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.surface.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    /// 信号雷达免责声明（弹层）。雷达把多只标的的买卖点集中展示，比单只标的的详情页
    /// 更容易被当成操作清单，所以要求阅读并勾选同意；同意过不再弹，见 RadarConsent。
    /// 口吻是规范的免责声明：客观说明功能性质与局限，不对用户说教。
    private var consentView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text")
                        .font(.system(size: 30)).foregroundColor(Theme.accent)
                    Text(L("市场雷达免责声明"))
                        .font(.headline).foregroundColor(Theme.textPrimary)
                }
                .frame(maxWidth: .infinity)

                Text(L("市场雷达基于公开行情数据，按缠论结构规则自动识别并汇总所选指数成分股的买卖点形态，供技术分析研究使用。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 10) {
                    consentPoint(L("本功能展示的内容均为按标准缠论技术分析规则得出的结果，不构成任何投资建议、证券推荐或买卖要约。"))
                    consentPoint(L("每个买卖点都只是缠论对价格结构的一次孤立观测，是否值得操作需要你自己结合基本面、其他技术面和市场环境综合判断。"))
                    consentPoint(L("气泡的颜色、深浅与大小分别表示信号方向、形态强弱与买卖点类型，不代表对未来价格走势的判断或收益承诺。"))
                    consentPoint(L("缠论结构随后续行情更新而调整，已显示的信号可能被修正或失效。"))
                    consentPoint(L("行情数据来自第三方，可能存在延迟或误差。"))
                    consentPoint(L("证券投资存在风险，投资决策及其结果由投资者独立判断并承担。"))
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Button {
                    consentChecked.toggle()
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: consentChecked ? "checkmark.square.fill" : "square")
                            .font(.system(size: 20))
                            .foregroundColor(consentChecked ? Theme.accent : Theme.textSecondary)
                        Text(L("我已阅读并理解上述免责声明"))
                            .font(.footnote).foregroundColor(Theme.textPrimary)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(consentChecked ? [.isSelected] : [])

                Button {
                    consent.agree()
                    showConsent = false
                } label: {
                    Text(consentButtonText)
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity).padding(.vertical, 13)
                        .background(canConfirmConsent ? Theme.accent : Theme.accent.opacity(0.35))
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(!canConfirmConsent)
                .animation(.default, value: consentSecondsRemaining)
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // 每次挂载（含首次进入、勾选状态被外部重置后再次出现）都从头倒数 10 秒；
        // 视图消失（如切到别的 Tab）时 Task 自动取消，回来再重新计时，不留半截状态。
        .task {
            consentSecondsRemaining = Self.consentMinReadSeconds
            while consentSecondsRemaining > 0 {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                consentSecondsRemaining -= 1
            }
        }
    }

    /// 勾选 + 满 10 秒阅读时长，两者都满足才放行。
    private var canConfirmConsent: Bool { consentChecked && consentSecondsRemaining <= 0 }

    /// 按钮文案随状态推进：倒计时中 → 勾了但没到时间 → 都满足。
    private var consentButtonText: String {
        if consentSecondsRemaining > 0 {
            return L("请仔细阅读（%lld 秒）", consentSecondsRemaining)
        } else if !consentChecked {
            return L("请先勾选上方确认")
        } else {
            return L("同意并查看")
        }
    }

    private func consentPoint(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text("•").foregroundColor(Theme.textSecondary)
            Text(text).font(.footnote).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// 点气泡 → 直接跑分析，成功后 push 详情页（不经过分析 Tab 的条件页）。
    /// 带上气泡上的真实名称（如「中芯国际」），供结果页加自选时存名称。
    ///
    /// 关键：让详情页与雷达完全同口径。这里传 end=雷达数据日(as_of)、start=end-270 天
    /// （270 = 雷达的 warmup(180) + window*2(90)）；详情接口始终在 start 之前再预热 180 天
    /// （warmupDays 参数已被后端忽略），与雷达取数起点 _fetch_start 完全一致，买卖点集合
    /// 与雷达相同（后端测试 test_chan_window_alignment 守护）。anchorDate 为气泡日期
    /// （信号出现日），详情页列表显示的也是出现日，图上标记则在所属笔的极值 K 线。
    ///
    /// 未订阅会员时（含点开免费预览那一天）这次分析跟分析 Tab 一样走每日免费额度
    /// （usage.canUseFree/recordUse），额度用尽弹付费墙，不能绕开——免费预览只是
    /// 多给了一天可点的真实信号，不是无限次分析的后门。
    private func openSymbol(_ symbol: String, name: String? = nil) {
        // 示例股（英伟达/茅台/腾讯）不扣额度，见 AppConfig.sampleSymbols
        let chargesQuota = !store.isSubscribed && !AppConfig.isSampleSymbol(market: vm.market, symbol: symbol)
        if chargesQuota && !usage.canUseFree(symbol: symbol) {
            showPaywall = true
            return
        }
        // 截止到「现在」：详情页要有最新K线（盘中也是）。之前截止到雷达扫描日 as_of，A 股/港股
        // 盘中点进去永远只有前一交易日。起点仍按 as_of 往前 270 天，与雷达扫描窗口的左端对齐，
        // 结构尽量一致；右端多出来的新K线可能改写最新几笔，弹层已说明「以详情页为准」。
        let m = vm.market.rawValue
        let asOf = QueryDates.date(from: vm.response?.asOf ?? "", market: m) ?? Date()
        let start = QueryDates.adding(days: -270, to: asOf, market: m)
        let end = Date()
        chanVM.apply(
            // 名称为空（美股无中文名）时不传，详情页标题退回显示代码
            market: vm.market, symbol: symbol, name: (name?.isEmpty ?? true) ? nil : name,
            startDate: start, endDate: end, freq: "daily", warmupDays: 0,
            // 雷达快照日期：详情页据此把可见窗口居中、画一条竖线标出来，
            // 让用户看得出分析的是雷达上正在看的那一天，不是默认的「最新」。
            anchorDate: vm.selectedDay?.date)
        Task {
            await chanVM.runAnalysis()
            if chanVM.errorMessage == nil, chanVM.analysis != nil {
                if chargesQuota { usage.recordUse(symbol: symbol) }
                showResults = true
            }
        }
    }

    /// 跑分析期间盖在信号页上的等待态，文案与分析 Tab 保持一致。
    private var analysisLoadingOverlay: some View {
        ZStack {
            Theme.background.opacity(0.85).ignoresSafeArea()
            VStack(spacing: 12) {
                ProgressView().tint(Theme.accent)
                Text(L("正在拉取行情并计算缠论结构…"))
                    .font(.subheadline).foregroundColor(Theme.textSecondary)
            }
        }
    }

    // MARK: - 说明行

    private var metaRow: some View {
        // 指数名称在雷达左上角的切换器里；这行是日期、更新时间与当天买卖点数（点开看全部信号）。
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let day = vm.selectedDay {
                Text(day.date)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                if day.id == vm.response?.days.first?.id {
                    // 次级别结论只对最新交易日算、盘中每 30 分钟刷新：标出更新时刻，
                    // 与点进详情看到的实时结论有出入时，用户知道差在时间上。之前只在
                    // 当天有共振徽标时才显示这行，导致共振本来就少的港股/A股几乎
                    // 看不到更新时间；改成只要最新一天算过次级别就显示，三个市场一致。
                    if let updated = vm.response?.subLevelUpdatedText {
                        Text(L("次级别 %@ 更新", updated))
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                    // 有成分股拉数失败、后台还在补算：告诉用户榜单还会补全，不是漏了
                    if let pending = vm.response?.pendingSymbols, pending > 0 {
                        Text(L("%lld 只补算中", pending))
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                } else if let computed = vm.selectedDayComputedAtText {
                    // 翻看历史某一天：这天的气泡是上一次全量扫描（computed_at）算出来的
                    // 快照，缠论笔在数据右端本身就是临时性的，之后如果又跑过新的扫描、
                    // 有更多K线进来，同一只股票在这天的买卖点可能已经变了——点进详情页
                    // 是用当下最新数据重新算，跟这份快照对不上是预期行为，不是 bug。
                    // 标出算出时刻，用户能明白「点进去可能不一样」的原因在这。
                    Text(L("数据 %@ 计算", computed))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
            }
            Spacer(minLength: 8)
            if let day = vm.selectedDay {
                // 当天（选了行业时为该行业）的买卖点数；点开是全部信号列表
                Button { panel = .signals } label: {
                    HStack(spacing: 4) {
                        Text(L("%lld 买点", day.buyCount)).foregroundColor(Theme.up)
                        Text("·").foregroundColor(Theme.textSecondary)
                        Text(L("%lld 卖点", day.sellCount)).foregroundColor(Theme.down)
                        if !day.candidates.isEmpty {
                            Text("·").foregroundColor(Theme.textSecondary)
                            Text(L("%lld 待确认", day.candidates.count)).foregroundColor(Theme.textSecondary)
                        }
                        Image(systemName: "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundColor(Theme.textSecondary.opacity(0.7))
                    }
                    .font(.caption.weight(.semibold).monospacedDigit())
                }
                .buttonStyle(.plain)
                .disabled(needsConsent)
                .accessibilityLabel(L("查看全部信号"))
            }
        }
    }

    // MARK: - 气泡场

    /// 气泡场的背景装饰：中心光晕 + 同心参考环。
    @ViewBuilder
    private func fieldDecoration(width w: Double, height h: Double) -> some View {
        let base = min(w, h)
        // 参考环与气泡共用的内缩场半轴：椭圆填满画布，长边不再留大片空白。
        let (hRad, vRad) = SignalRadarView.fieldRadii(width: w, height: h)

        // 由近及远的光晕：中心亮、向外自然变暗，"越靠中心=越新"不用靠文字说明，
        // 图本身就有纵深感。
        RadialGradient(
            colors: [Theme.accent.opacity(0.20), Theme.accent.opacity(0.0)],
            center: .center, startRadius: 0, endRadius: base * 0.55
        )
        .frame(width: CGFloat(w), height: CGFloat(h))

        // 同心参考环：越外越淡，呼应同一套"近实远虚"的纵深语言。环上的时间标签画在气泡上层
        // （ringLabels），气泡按时间分圈带摆（layoutRingField）。
        ForEach(Array(SignalRadarView.ringSpecs.enumerated()), id: \.offset) { idx, spec in
            // 横向椭圆：左右宽、上下窄，与气泡摆位同一套半轴
            let rx = hRad * spec.scale
            let ry = vRad * spec.scale
            Ellipse()
                .stroke(Theme.textSecondary.opacity(0.16 - Double(idx) * 0.045),
                        style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                .frame(width: CGFloat(rx * 2), height: CGFloat(ry * 2))
                .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
        }
    }

    /// 环上时间标签：当日 / 3天内 / 7天内，小胶囊、画在气泡上层（位置见 ringLabelBoxes，摆位已避开）。
    private func ringLabels(width w: Double, height h: Double) -> some View {
        ForEach(Array(zip(SignalRadarView.ringSpecs.indices, SignalRadarView.ringLabelBoxes(width: w, height: h, labels: gradeRingLabels))), id: \.0) { i, box in
            Text(gradeRingLabels?[i] ?? SignalRadarView.ringSpecs[i].label)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(Theme.textSecondary)
                .frame(width: CGFloat(box.width), height: CGFloat(box.height))
                .background(Theme.background.opacity(0.85), in: Capsule())
                .overlay(Capsule().stroke(Theme.border, lineWidth: 0.6))
                .position(x: CGFloat(box.x + box.width / 2), y: CGFloat(box.y + box.height / 2))
                .allowsHitTesting(false)
        }
    }

    private var bubbleField: some View {
        GeometryReader { geo in
            let w = Double(geo.size.width)
            let h = Double(geo.size.height)
            let dayDate = fieldDay?.date ?? ""
            let signals = fieldDay?.signals ?? []
            // 「待确认」候选（最后一笔还没走完，按严格口径尚不成立）不画进雷达，只在上方一行显示个数：
            // 画成灰色虚线气泡会和真实买卖点挤在一起，雷达又满了
            let candidates: [RadarSignal] = []
            let candidateIDs = Set(candidates.map(\.id))
            // 全部都已确认（严格口径恒如此）时不画「✓」：每个气泡都有，等于没有
            let marksConfirmed = !signals.allSatisfy(\.confirmed)
            let sectorMode = radarTab == .chan && isSectorField
            let order = vm.sectorOrder
            let board = vm.selectedSectorBoard
            let avoid = fieldObstacles(width: w)
            // 摆位很重（逐个排字号 + 几百轮推开），只在输入真的变了时重算：点气泡、开面板、
            // 后台轮询等与气泡无关的刷新直接复用上一次的结果，否则每次都卡几帧
            let key = FieldLayoutKey(
                signals: signals, candidates: candidates, sectorMode: sectorMode, order: order,
                rs: order.map { k in board?.sectors.first(where: { $0.key == k })?.rsVsMarket },
                names: order.map { vm.sectorName($0) }, dayDate: dayDate, width: w, height: h,
                avoid: avoid.map { [$0.x, $0.y, $0.width, $0.height] }, gradeRings: gradeRingLabels)
            let field = layoutCache.value(for: key) {
                sectorMode
                    ? SignalRadarView.layoutSectorField(
                        signals: signals, order: order, names: { vm.sectorName($0) },
                        rsLookup: { k in board?.sectors.first(where: { $0.key == k })?.rsVsMarket },
                        dayDate: dayDate, width: w, height: h, avoid: avoid)
                    : SignalRadarView.layoutRingField(
                        signals: signals + candidates, dayDate: dayDate, width: w, height: h, avoid: avoid,
                        gradeRings: gradeRingLabels)
            }
            ZStack {
                if sectorMode {
                    sectorDecoration(field.wedges, width: w, height: h)
                } else {
                    fieldDecoration(width: w, height: h)
                }

                if field.bubbles.isEmpty {
                    Text(radarTab == .fundamental ? L("当日无评级升降") : L("当日无买卖点信号"))
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                } else {
                    ForEach(field.bubbles) { layout in
                        RadarBubble(
                            signal: layout.signal,
                            metrics: layout.metrics,
                            baseX: CGFloat(layout.x),
                            baseY: CGFloat(layout.y),
                            phase: layout.phase,
                            color: SignalRadarView.bubbleColor(
                                side: layout.signal.side,
                                depth: SignalFormatting.strengthDepth(layout.signal.signalStrength)),
                            isNew: radarTab == .chan && layout.signal.date == dayDate,
                            isCandidate: candidateIDs.contains(layout.signal.id),
                            marksConfirmed: marksConfirmed,
                            // 点气泡直接进分析详情页（不再先弹底部面板）
                            onOpen: { openSymbol(layout.signal.symbol, name: layout.signal.name) }
                        )
                        // 气泡任何时候都不做透明处理：刷新完直接出现，不淡入
                        .transition(.identity)
                    }
                }

                if !sectorMode {
                    ringLabels(width: w, height: h)
                }
                if sectorMode {
                    ForEach(field.wedges) { wedge in
                        wedgeLabel(wedge)
                    }
                } else if field.hidden + hiddenExtra > 0 {
                    // 同心环最多画 ringFieldCap 个最新的，其余在「当日信号」里看全（基本面 tab：前 10 只，其余看全部评级升降）
                    Button { if radarTab == .fundamental { showGradeAll = true } else { panel = .signals } } label: {
                        Text(L("另有 %lld 个 · 查看全部", field.hidden + hiddenExtra))
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(Theme.accent)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Theme.surface.opacity(0.92), in: Capsule())
                            .overlay(Capsule().stroke(Theme.border, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .position(x: CGFloat(w / 2), y: CGFloat(h - 18))
                }
            }
        }
        // 画布吃满上下控件之外的全部空间（不再套固定宽高比）：GeometryReader 拿到的就是整块画布，
        // 环 / 扇区与气泡按它的中心摆，椭圆半轴见 fieldRadii。
        .frame(maxWidth: .infinity, minHeight: SignalRadarView.fieldMinHeight, maxHeight: .infinity)
        .background(
            RadialGradient(
                colors: [Color(hex: 0x131A26), Theme.background],
                center: .center, startRadius: 6, endRadius: 280
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    /// 雷达画布是否按行业分扇区。**当前关闭**：顶部漏斗已经按「大盘环境 → 最强行业 → 当日信号」
    /// 往下引，雷达只管陈列信号、按时间排（越靠中心越新），不再重复切行业；行业强弱看「最强行业」一行。
    /// 扇区摆位代码（SectorRadarLayout）与测试保留，改回 true 即恢复。
    static let sectorFieldEnabled = false

    /// 雷达画布当前画的那一天：缠论 tab = 选中日的买卖点；基本面 tab = 选中日在场的评级升降（同一块画布）。
    private var fieldDay: RadarDay? {
        radarTab == .fundamental ? gradeVM.radarDay : vm.selectedDay
    }

    /// 基本面 tab 的环文字（由内向外）：环 = 新等级；缠论 tab 为 nil（环 = 距查看日的交易日数，文字见 ringSpecs）。
    private var gradeRingLabels: [String]? {
        radarTab == .fundamental ? ["A", "B", L("C 及以下")] : nil
    }

    /// 画布之外被折叠的只数（基本面 tab 前 10 只之外的）。
    private var hiddenExtra: Int { radarTab == .fundamental ? gradeVM.hiddenCount : 0 }

    private var isSectorField: Bool {
        SignalRadarView.sectorFieldEnabled && vm.selectedDay?.hasSectorData == true
    }

    /// 叠在雷达上的控件占的区域，气泡摆位时避开。指数切换器已并进顶部市场分段条，画布里没有叠加控件，所以为空。
    /// （以前是左上角固定预留 150 × 40：实测按钮大小会在量出来后让气泡重摆、跳一下。）
    private func fieldObstacles(width w: Double) -> [RadarOrbitSpacing.Obstacle] { [] }

    // MARK: - 扇区（行业）

    /// 行业状态配色（逐利红 / 避险绿 / 观望灰）；没有强弱数据时灰。
    private func sectorTint(_ key: String) -> Color {
        MarketHeader.regimeColor(vm.selectedSectorBoard?.sectors.first(where: { $0.key == key })?.label)
    }

    /// 扇区分隔：不画底色，每个行业一块楔形只描一条细边线。
    private func sectorDecoration(_ wedges: [WedgeLabel], width w: Double, height h: Double) -> some View {
        let (hRad, vRad) = SignalRadarView.fieldRadii(width: w, height: h)
        // 不画底色，只画扇区之间的细分隔线（行业状态色在扇区标签上）
        let shapes = wedges.map(\.wedge)
        return ZStack {
            Canvas { ctx, _ in
                for wedge in shapes {
                    var path = Path()
                    path.move(to: CGPoint(x: w / 2, y: h / 2))
                    let steps = 24
                    for k in 0...steps {
                        let a = wedge.center - wedge.halfWidth + 2 * wedge.halfWidth * Double(k) / Double(steps)
                        let p = SectorRadarLayout.point(angle: a, radius: 1, width: w, height: h, hRad: hRad, vRad: vRad)
                        path.addLine(to: CGPoint(x: p.x, y: p.y))
                    }
                    path.closeSubpath()
                    ctx.stroke(path, with: .color(Theme.border.opacity(0.8)), lineWidth: 0.6)
                }
            }
        }
        .frame(width: CGFloat(w), height: CGFloat(h))
        .allowsHitTesting(false)
    }

    /// 扇区标签：行业名 + 相对大盘强弱，画不下的气泡数「+N」；点开行业面板。
    private func wedgeLabel(_ label: WedgeLabel) -> some View {
        Button { panel = .sector(label.wedge.key) } label: {
            HStack(spacing: 3) {
                Text(label.name).font(.system(size: 10, weight: .semibold))
                if let rs = label.rs {
                    Text(SectorBoardList.rsText(rs)).font(.system(size: 9).monospacedDigit())
                }
                if label.wedge.hidden > 0 {
                    Text("+\(label.wedge.hidden)")
                        .font(.system(size: 9, weight: .bold).monospacedDigit())
                        .foregroundColor(Theme.accent)
                }
            }
            .foregroundColor(sectorTint(label.wedge.key) == Theme.textSecondary ? Theme.textPrimary.opacity(0.8)
                             : sectorTint(label.wedge.key))
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(Theme.background.opacity(0.82), in: Capsule())
            .overlay(Capsule().stroke(sectorTint(label.wedge.key).opacity(0.5), lineWidth: 0.8))
        }
        .buttonStyle(.plain)
        .position(x: CGFloat(label.x), y: CGFloat(label.y))
        .accessibilityLabel(L("%@，%lld 个在场信号", label.name, label.wedge.total))
    }

    // MARK: - 面板

    /// 面板共用的当日事实；还没有选中日时为 nil。
    private var factContext: RadarFactContext? {
        guard let day = vm.selectedDay else { return nil }
        return RadarFactContext(
            market: vm.market, day: day, board: vm.selectedSectorBoard, order: vm.sectorOrder,
            sectorName: { vm.sectorName($0) })
    }

    /// 面板列表里点某一行：先收起面板，收起后（sheet 的 onDismiss）再跑分析、push 详情页。
    private func openDetail(_ signal: RadarSignal) {
        pendingDetail = signal
        panel = nil
    }

    @ViewBuilder
    private func panelView(_ panel: RadarPanel) -> some View {
        switch panel {
        case .environment:
            MacroDetailSheet(market: vm.market, panic: panicVM.responses[vm.market])
        case .sectorPicker:
            if let day = vm.baseSelectedDay {
                SectorBoardSheet(
                    market: vm.market, date: day.date,
                    radar: SectorRadarContext(universeName: currentUniverseName, date: day.date,
                                              counts: day.sectorCounts ?? [:], selectedKey: vm.sectorFilter,
                                              totals: (day.buyCount, day.sellCount)),
                    onPick: { key, _ in vm.setSectorFilter(key) },
                    onClear: { vm.setSectorFilter(nil) })
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
            }
        case .sector(let key):
            if let ctx = factContext {
                RadarSectorSheet(context: ctx, initialKey: key, onOpenDetail: openDetail)
            }
        case .signals:
            if let ctx = factContext {
                RadarSignalListSheet(context: ctx, universeName: currentUniverseName, onOpenDetail: openDetail)
            }
        }
    }

    // MARK: - universe 切换器（雷达左上角）

    /// 当前指数展示名（见 `SignalRadarViewModel.activeUniverseName`）。指数切换已并进顶部市场分段条
    /// （点已选中的市场弹出该市场的指数列表），画布里不再有切换器。
    private var currentUniverseName: String { vm.activeUniverseName }

    /// 按实际天数确定半径，按时间环带统一均分方向，避让不改变时间半径。
    private struct BubbleLayout: Identifiable {
        let signal: RadarSignal
        let metrics: RadarBubbleMetrics
        var diameter: Double { metrics.diameter }
        var x: Double
        var y: Double
        let phase: Double
        let daysAgo: Int
        var id: String { signal.id }
    }

    /// 三个等距参考环：当日 1/3、3 天 2/3、1 周 1.0，与气泡同一套时间半径映射
    /// （RadarOrbitSpacing.timeRadius）。「当日」指当前查看的那一天，不一定是今天。
    /// 用计算属性而非 static let：L() 依赖运行时语言设置，static let 只会算一次，
    /// 用户切换语言后文案不会跟着变。
    static var ringSpecs: [(scale: Double, label: String)] {
        [(1.0 / 3, L("当日")), (2.0 / 3, L("3天内")), (1.0, L("7天内"))]
    }

    /// 场边距：最外环（scale 1.0）到容器四边留出的空白，给气泡的阴影 + 右上角「新」
    /// 角标 + 拖拽放大留余量。以前最外环半径直接取 min(w,h)/2，环线正好压在容器边上，
    /// 落在最外环、角度又指向边缘的气泡（尤其是那颗被推到远端的孤立卖点）就会被
    /// 圆角容器裁掉一半。现在把「场半径」整体内缩这个边距，环线和气泡一起内移。
    static let fieldInset: Double = 18
    /// 画布最小高度（小屏上方控件多时也保证雷达可用）；正常情况下画布吃满剩余高度。
    static let fieldMinHeight: CGFloat = 240
    /// 椭圆纵/横半轴比上限：画布改为吃满剩余高度后会比以前高，上限放到 1.0（最多是正圆），
    /// 让环和气泡跟着用满纵向空间，而不是在上下留出大片空白。
    static let ellipseRatio: Double = 1.0

    /// 气泡场的水平/垂直半轴：各方向取 (边长/2 - fieldInset)。以前用单一 min(w,h)/2
    /// 圆半径，画布一旦不是正方形（信号页画布通常比它高要宽），圆就卡在短边上、长边
    /// 留大片空白。改成两个半轴后，参考环与气泡摆位是一个填满画布的椭圆，把空间尽量
    /// 用满；ringRadius 返回「占半轴的分数(0~1)」，各轴乘各自半轴。
    static func fieldRadii(width w: Double, height h: Double) -> (h: Double, v: Double) {
        let hRad = max(0, w / 2 - fieldInset)
        // 纵向半轴不超过横向的 ellipseRatio：左右宽、上下窄的椭圆
        return (hRad, max(0, min(h / 2 - fieldInset, hRad * ellipseRatio)))
    }

    /// 时间距离 → 半径（见 RadarOrbitSpacing.timeRadius）：今天在圆心。
    static func ringRadius(forDaysAgo daysAgo: Int, fieldRadius: Double) -> Double {
        RadarOrbitSpacing.timeRadius(daysAgo: daysAgo) * fieldRadius
    }

    /// daysAgo（交易日）→ 时间档：0=今天、1=3天内、2=一周内（含更早，最多保留 5 个交易日）。
    static func bandIndex(forDaysAgo daysAgo: Int) -> Int {
        daysAgo <= 0 ? 0 : (daysAgo <= 3 ? 1 : 2)
    }

    /// 越远越小（按天连续递减，见 RadarOrbitSpacing.timeSizeFactor），和「买卖点类型」的
    /// 大小是叠乘关系：外圈越久远的信号越小，也更塞得下。
    static func ringSizeFactor(forDaysAgo daysAgo: Int) -> Double {
        RadarOrbitSpacing.timeSizeFactor(daysAgo: daysAgo)
    }

    /// 气泡摆位：离中心的相对距离严格由时间决定（横向椭圆轨道），优先横向摆放。
    ///
    /// - 半径 = ringRadius(daysAgo) × 场半径（当天为圆心），同一天共用一条圆轨道；同一天
    ///   多个气泡放不下时才外扩到刚好排开，且不越过所在时间档外沿（RadarOrbitSpacing.orbitRadius）。
    /// - 方向：由内圈到外圈、大气泡先放，每个气泡在自己的椭圆轨道上选「重叠最少、尽量
    ///   横向」的方向（RadarOrbitSpacing.bestAngle）。
    /// - 避让：最后做一轮碰撞松弛（RadarOrbitSpacing.relax）。允许边缘重叠较小气泡直径的
    ///   bubbleOverlapRatio（代码/名称在气泡中间，盖不到），同时每个气泡被拉回自己的时间环——
    ///   以前要求完全不重叠，10 个气泡只能被挤成一整圈铺满画布，远近不再对应时间，
    ///   看不出哪个是哪天的。新的在上层（见末尾排序），重叠处被盖住的是更旧的气泡边缘。
    private static func layoutBubbles(
        signals: [RadarSignal], dayDate: String, width w: Double, height h: Double,
        avoid: [RadarOrbitSpacing.Obstacle] = []
    ) -> [BubbleLayout] {
        guard !signals.isEmpty else { return [] }
        let (hRad, vRad) = fieldRadii(width: w, height: h)
        // 椭圆轨道：相对半径 r（= 时间）对应横半轴 r·hRad、纵半轴 r·vRad；放不下时按平均半轴外扩
        let meanRadius = ((hRad * hRad + vRad * vRad) / 2).squareRoot()
        let center = (x: w / 2, y: h / 2)
        let scales = ringSpecs.map(\.scale)
        func age(_ s: RadarSignal) -> Int { s.ageDays ?? daysAgo(from: s.date, to: dayDate) }
        let maxDiameter = max(1, min(w, h) - 2 * RadarBubbleMetrics.edgePadding)
        // 每次布局每个信号只测量一次，排序和避让都使用最终尺寸。
        let bases = signals.map { diameter(forLevel: $0.level) * ringSizeFactor(forDaysAgo: age($0)) }
        // 当天信号特别集中时统一缩小，保证推开避让有地方可去（一二三类的大小关系不变）
        let crowd = RadarOrbitSpacing.crowdScale(diameters: bases, width: w, height: h)
        let metrics = zip(signals, bases).map { signal, base in
            RadarBubbleMetrics(symbol: signal.symbol, name: signal.name,
                               baseDiameter: base * crowd, maxDiameter: maxDiameter)
        }
        let sizedSignals = Array(zip(signals, metrics))
        let byDay = Dictionary(grouping: sizedSignals) { age($0.0) }
        var layouts: [BubbleLayout] = []
        var placed: [RadarOrbitSpacing.Placed] = []
        var anchors: [RadarOrbitSpacing.Anchor] = []
        for (orbitIndex, days) in byDay.keys.sorted().enumerated() {
            // 大气泡先占位；同尺寸按稳定标识排序，强度排名变化时气泡不互换位置
            let members = (byDay[days] ?? []).sorted {
                ($0.1.diameter, $1.0.id) > ($1.1.diameter, $0.0.id)
            }
            let r = RadarOrbitSpacing.orbitRadius(
                timeRadius: ringRadius(forDaysAgo: days, fieldRadius: 1),
                diameters: members.map { $0.1.diameter }, fieldRadius: meanRadius,
                cap: scales[bandIndex(forDaysAgo: days)])
            let rx = r * hRad, ry = r * vRad
            // 首选方向在右、左之间交替：气泡优先铺在横向
            let preferred = orbitIndex % 2 == 0 ? 0 : Double.pi
            for (sig, metrics) in members {
                let d = metrics.diameter
                let angle = RadarOrbitSpacing.bestAngle(
                    radiusX: rx, radiusY: ry, diameter: d, center: center, placed: placed, preferred: preferred)
                let inset = d / 2 + RadarBubbleMetrics.edgePadding
                let x = min(max(center.x + rx * cos(angle), inset), max(inset, w - inset))
                let y = min(max(center.y + ry * sin(angle), inset), max(inset, h - inset))
                placed.append(.init(x: x, y: y, diameter: d))
                anchors.append(.init(rx: rx, ry: ry))
                layouts.append(BubbleLayout(signal: sig, metrics: metrics, x: x, y: y,
                                            phase: Double(layouts.count) * 0.35, daysAgo: days))
            }
        }
        // 按时间摆完后推开压得太多的气泡：允许边缘少量重叠，并把每个气泡拉回自己的时间环
        let relaxed = RadarOrbitSpacing.relax(
            layouts.map { .init(x: $0.x, y: $0.y, diameter: $0.diameter) },
            width: w, height: h, inset: RadarBubbleMetrics.edgePadding, obstacles: avoid,
            overlapRatio: bubbleOverlapRatio, anchors: anchors)
        for i in layouts.indices {
            layouts[i].x = relaxed[i].x
            layouts[i].y = relaxed[i].y
        }
        // 叠层：越接近查看日（daysAgo 越小）画得越晚，重叠时新的浮在上面
        layouts.sort { $0.daysAgo > $1.daysAgo }
        return layouts
    }

    /// 气泡摆位的全部输入；相同输入复用上一次的摆位结果（见 bubbleField）。
    private struct FieldLayoutKey: Equatable {
        let signals: [RadarSignal]
        let candidates: [RadarSignal]
        let sectorMode: Bool
        let order: [String]
        let rs: [Double?]
        let names: [String]
        let dayDate: String
        let width: Double
        let height: Double
        let avoid: [[Double]]
        let gradeRings: [String]?
    }

    /// 只缓存最近一次摆位。引用类型、不发布变化：写入缓存不会再触发一次刷新。
    private final class FieldLayoutCache {
        private var key: FieldLayoutKey?
        private var field: FieldLayout?

        func value(for key: FieldLayoutKey, compute: () -> FieldLayout) -> FieldLayout {
            if let field, self.key == key { return field }
            let fresh = compute()
            self.key = key
            field = fresh
            return fresh
        }
    }

    /// 一次摆位的结果：气泡、扇区标签（同心环模式为空）、没画出来的信号数（同心环模式）。
    private struct FieldLayout {
        var bubbles: [BubbleLayout]
        var wedges: [WedgeLabel] = []
        var hidden: Int = 0
    }

    /// 扇区标签：所属扇区 + 展示名 + 相对大盘强弱 + 画布上的位置。
    private struct WedgeLabel: Identifiable {
        let wedge: SectorRadarLayout.Wedge
        let name: String
        let rs: Double?
        var x: Double
        var y: Double
        let width: Double
        static let height = 18.0
        var id: String { wedge.key }
    }

    /// 同心环模式最多尝试画这么多个最新的气泡；放不下的与超出的都在「当日信号」面板里看全。
    static let ringFieldCap = 24

    /// 信号数不超过这个值时，同心环模式保证全部画出来（放不下就放宽圈带、缩小气泡），不出现「另有 N 个」；
    /// 超过才只画最新的 ringFieldCap 个、其余折叠到「另有 N 个 · 查看全部」。
    static let ringShowAllLimit = 10

    /// 同心环模式：按时间分三圈带摆——当日在最里圈、3 天内在中间、7 天内在最外圈（与环上标签一致，
    /// 见 ringSpecs / bandIndex）。每圈带里用 SectorRadarLayout.pack 把整圆当一个扇区，由内向外、互不重叠，
    /// 外圈避开里圈已摆好的；某圈带放不下的计入「另有 N 个」（信号数 ≤ ringShowAllLimit 时例外：放宽圈带、缩小气泡也要全画出来）。后端已按出现时间从新到旧排好。
    private static func layoutRingField(
        signals: [RadarSignal], dayDate: String, width w: Double, height h: Double,
        avoid: [RadarOrbitSpacing.Obstacle], gradeRings: [String]? = nil
    ) -> FieldLayout {
        guard !signals.isEmpty else { return FieldLayout(bubbles: []) }
        let shown = Array(signals.prefix(ringFieldCap))
        func age(_ s: RadarSignal) -> Int { s.ageDays ?? daysAgo(from: s.date, to: dayDate) }
        let ages = shown.map(age)
        let (hRad, vRad) = fieldRadii(width: w, height: h)

        let maxDiameter = max(1, min(w, h) - 2 * RadarBubbleMetrics.edgePadding)
        // 基本面 tab（gradeRings 非空）：环 = 新等级、大小 = 变档数，不再按「越久越小」缩放
        let bases = zip(shown, ages).map { diameter(forLevel: $0.level) * (gradeRings == nil ? ringSizeFactor(forDaysAgo: $1) : 1) }
        let obstacles = avoid.map { SectorRadarLayout.Rect(x: $0.x, y: $0.y, width: $0.width, height: $0.height) }
            + ringLabelBoxes(width: w, height: h, labels: gradeRings)

        // 每圈带的圆心范围：在两条环线之间、略收窄，气泡看得出落在哪一圈（不压在环线正中）
        let bands: [ClosedRange<Double>] = [0.0...0.27, 0.42...0.62, 0.76...1.0]
        let whole = SectorRadarLayout.Wedge(key: "_all", center: 0, halfWidth: .pi, total: shown.count, shown: shown.count)

        /// 按给定缩放摆一次：scale 在整体拥挤缩放之上再缩（直径下限由 RadarBubbleMetrics 兜底）；
        /// relaxBands 时不再限制在各自的时间圈带里，整个圆内都可以摆（仍由内向外、越新越靠里）。
        func attempt(scale: Double, relaxBands: Bool) -> (placed: [SectorRadarLayout.Placement], metrics: [RadarBubbleMetrics]) {
            let crowd = RadarOrbitSpacing.crowdScale(diameters: bases, width: w, height: h) * scale
            let metrics = zip(shown, bases).map {
                RadarBubbleMetrics(symbol: $0.symbol, name: $0.name, baseDiameter: $1 * crowd, maxDiameter: maxDiameter)
            }
            var placed: [SectorRadarLayout.Placement] = []
            for band in 0..<ringSpecs.count {
                let members = shown.indices.filter { bandIndex(forDaysAgo: ages[$0]) == band }
                guard !members.isEmpty else { continue }
                let slots = members.map { SectorRadarLayout.Slot(index: $0, wedgeKey: whole.key, angle: 0, radius: 0) }
                let packed = SectorRadarLayout.pack(
                    plan: ([whole], slots), diameters: metrics.map(\.diameter), width: w, height: h,
                    hRad: hRad, vRad: vRad, edge: RadarBubbleMetrics.edgePadding, obstacles: obstacles,
                    outwardOnly: false, radiusRange: relaxBands ? 0.0...1.0 : bands[band], existing: placed)
                placed += packed.placements
            }
            return (placed, metrics)
        }

        var result = attempt(scale: 1, relaxBands: false)
        if signals.count <= ringShowAllLimit {
            // 不超过 ringShowAllLimit 个：必须全部画出来、不出现「另有 N 个」——先放宽时间圈带，再逐步缩小气泡
            for scale in [1.0, 0.85, 0.7, 0.55] where result.placed.count < shown.count {
                result = attempt(scale: scale, relaxBands: true)
            }
        }
        let placed = result.placed
        let metrics = result.metrics
        var layouts = placed.map { p in
            BubbleLayout(signal: shown[p.index], metrics: metrics[p.index], x: p.x, y: p.y,
                         phase: Double(p.index) * 0.35, daysAgo: ages[p.index])
        }
        layouts.sort { $0.daysAgo > $1.daysAgo }
        return FieldLayout(bubbles: layouts, hidden: signals.count - layouts.count)
    }

    /// 环上时间标签（当日 / 3天内 / 7天内）的位置：各环正上方。标签画在气泡上层，摆位时当禁区避开。
    static func ringLabelBoxes(width w: Double, height h: Double, labels: [String]? = nil) -> [SectorRadarLayout.Rect] {
        let (_, vRad) = fieldRadii(width: w, height: h)
        return ringSpecs.enumerated().map { i, spec in
            let lw = labelWidth(labels?[i] ?? spec.label) - 2
            return SectorRadarLayout.Rect(x: w / 2 - lw / 2, y: h / 2 - vRad * spec.scale - ringLabelHeight / 2,
                                          width: lw, height: ringLabelHeight)
        }
    }

    static let ringLabelHeight = 16.0

    /// 标签宽度估算：中日韩字符约 10.5pt、其余约 6pt（10pt 字号）+ 左右内边距。
    private static func labelWidth(_ text: String) -> Double {
        text.reduce(12.0) { $0 + ($1.isASCII ? 6.0 : 10.5) }
    }

    /// 扇区模式：角度 = 行业（按 order 从强到弱、从上往下）。每个行业按信号数分名额（SectorRadarLayout.quotas），
    /// 再由 SectorRadarLayout.pack 直接摆进自己的扇区（扇区里越靠里越新；互不重叠，放不下的计入标签上的「+N」）。
    /// 不按时间半径摆好后推开：实测一天的信号大多是当日 / 前一日的，按时间半径全挤在圆心、叠成一团，推开后又跑出自己的扇区。
    private static func layoutSectorField(
        signals: [RadarSignal], order: [String], names: @escaping (String) -> String,
        rsLookup: @escaping (String) -> Double?,
        dayDate: String, width w: Double, height h: Double, avoid: [RadarOrbitSpacing.Obstacle]
    ) -> FieldLayout {
        guard !signals.isEmpty else { return FieldLayout(bubbles: []) }
        func age(_ s: RadarSignal) -> Int { s.ageDays ?? daysAgo(from: s.date, to: dayDate) }
        let ages = signals.map(age)
        let plan = SectorRadarLayout.plan(sectors: signals.map(\.sector), ages: ages, order: order)
        let (hRad, vRad) = fieldRadii(width: w, height: h)

        // 扇区标签（行业名 + 相对大盘强弱 +「+N」）：放在扇区中线的最外沿，夹回画布内。摆气泡前还不知道 N，按两位数预留宽度
        func labelBox(_ wedge: SectorRadarLayout.Wedge, hidden: String) -> WedgeLabel {
            let name = names(wedge.key)
            let rs = rsLookup(wedge.key)
            let lw = labelWidth(name + (rs.map { " " + SectorBoardList.rsText($0) } ?? "") + hidden)
            let p = SectorRadarLayout.point(angle: wedge.center, radius: 1, width: w, height: h, hRad: hRad, vRad: vRad)
            let x = min(max(p.x, lw / 2 + 4), max(lw / 2 + 4, w - lw / 2 - 4))
            let y = min(max(p.y, WedgeLabel.height / 2 + 4), max(WedgeLabel.height / 2 + 4, h - WedgeLabel.height / 2 - 4))
            return WedgeLabel(wedge: wedge, name: name, rs: rs, x: x, y: y, width: lw)
        }
        let reserved = plan.wedges.map { labelBox($0, hidden: " +99") }
        let obstacles = avoid.map { SectorRadarLayout.Rect(x: $0.x, y: $0.y, width: $0.width, height: $0.height) }
            + reserved.map { SectorRadarLayout.Rect(x: $0.x - $0.width / 2, y: $0.y - WedgeLabel.height / 2,
                                                    width: $0.width, height: WedgeLabel.height) }

        // 气泡尺寸：类型定大小、越久远越小，整体太挤时统一缩小（最小直径由 RadarBubbleMetrics 兜底）
        let maxDiameter = max(1, min(w, h) - 2 * RadarBubbleMetrics.edgePadding)
        let bases = plan.slots.map { diameter(forLevel: signals[$0.index].level) * ringSizeFactor(forDaysAgo: ages[$0.index]) }
        let crowd = RadarOrbitSpacing.crowdScale(diameters: bases, width: w, height: h)
        var metrics: [Int: RadarBubbleMetrics] = [:]
        var diameters = Array(repeating: RadarBubbleMetrics.minDiameter, count: signals.count)
        for (slot, base) in zip(plan.slots, bases) {
            let sig = signals[slot.index]
            let m = RadarBubbleMetrics(symbol: sig.symbol, name: sig.name, baseDiameter: base * crowd, maxDiameter: maxDiameter)
            metrics[slot.index] = m
            diameters[slot.index] = m.diameter
        }

        let packed = SectorRadarLayout.pack(plan: plan, diameters: diameters, width: w, height: h,
                                            hRad: hRad, vRad: vRad, edge: RadarBubbleMetrics.edgePadding,
                                            obstacles: obstacles)
        var layouts: [BubbleLayout] = []
        for p in packed.placements {
            guard let m = metrics[p.index] else { continue }
            layouts.append(BubbleLayout(signal: signals[p.index], metrics: m, x: p.x, y: p.y,
                                        phase: Double(layouts.count) * 0.35, daysAgo: ages[p.index]))
        }
        // 叠层：越新画得越晚
        layouts.sort { $0.daysAgo > $1.daysAgo }
        let labels = packed.wedges.map { labelBox($0, hidden: $0.hidden > 0 ? " +\($0.hidden)" : "") }
        return FieldLayout(bubbles: layouts, wedges: labels)
    }

    /// 允许两个气泡边缘重叠「较小直径 × 此比例」。0.2 时重叠最深处离被盖气泡中心仍有
    /// 约 0.6 个半径，中间的代码和名称不会被盖住；再大就开始压字。
    static let bubbleOverlapRatio: Double = 0.2

    /// 买卖点类型 → 气泡直径：一类 58 / 二类 72 / 三类 86。一类只是背驰迹象、尚待验证，最小；
    /// 三类回踩完全不回中枢、确认程度最高，最大。面积约 1 : 1.5 : 2.2——旧档位 62 / 88 / 116
    /// （面积 1 : 2 : 3.5）再叠时间系数后大小差到 2.6 倍、整体也偏大；现在仍能分出三档，
    /// 再叠上时间系数（越旧越小，最小卡在 RadarBubbleMetrics.minDiameter）与颜色深浅（强弱），三个维度各自看得清。
    static func diameter(forLevel level: Int) -> Double {
        switch level {
        case 1: return 58
        case 2: return 72
        default: return 86
        }
    }

    /// 信号诞生日 → 查看日的天数差（signal.date 恒 <= dayDate，见后端按日重建）。
    static func daysAgo(from signalDate: String, to viewedDate: String) -> Int {
        max(0, absDayDiff(signalDate, viewedDate))
    }

    /// 两个 yyyy-MM-dd 日期字符串相差多少天（可正可负；解析失败按 0 处理）。
    static func absDayDiff(_ a: String, _ b: String) -> Int {
        // 解析失败不能返回 0——0 意味着"完全匹配"，会在 jumpToNearestDay 的
        // 就近查找里把解析失败的项当成最佳命中，把日期选择器锁死在第一项上
        // （表现为用户选哪天点确定都跳不动）。解析失败时返回一个大数，让它
        // 永远选不中。
        guard let da = parser.date(from: a), let db = parser.date(from: b) else { return .max }
        return abs(Calendar(identifier: .gregorian).dateComponents([.day], from: da, to: db).day ?? 0)
    }

    /// 与详情页买卖点列表的强弱圆点共用同一套渐变色（深浅 = 信号强弱，同一口径）；
    /// 详情页 K 线图上的买卖点徽标只用红 / 绿纯色，不画深浅。
    static func bubbleColor(side: String, depth: Double) -> Color {
        SignalFormatting.radarColor(side: side, depth: depth)
    }

    // MARK: - 图例

    /// 一行说完颜色/大小/标签三件事，点右边的问号看完整算法说明（选股范围 + 排序公式），
    /// 不用把所有细节都堆在常驻图例里挤占气泡场的空间。
    private var legend: some View {
        HStack(spacing: 12) {
            HStack(spacing: 4) {
                Circle().fill(Theme.up).frame(width: 8, height: 8)
                Circle().fill(Theme.down).frame(width: 8, height: 8)
                // 颜色编码方向，深浅编码形态强弱（弱浅→强深），具体口径留给问号弹层。
                Text(L("深浅=信号强弱")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            HStack(spacing: 3) {
                sizeDot(diameter: SignalRadarView.diameter(forLevel: 1))
                sizeDot(diameter: SignalRadarView.diameter(forLevel: 3))
                Text(L("大小=一二三类")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            Text(isSectorField ? L("扇区=行业，上强下弱") : L("越靠中心越新"))
                .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                .lineLimit(1).minimumScaleFactor(0.8)
            Spacer(minLength: 4)
            algorithmInfoButton
        }
    }

    /// 图例里的大小参考点：真实按 `diameter(forLevel:)` 等比缩小展示，不带文字标签
    /// （一/二/三类的说明在算法说明弹层，这里只给一眼看出"有大有小"的直观印象）。
    private func sizeDot(diameter: Double) -> some View {
        Circle().fill(Theme.textSecondary).frame(width: diameter * 0.16, height: diameter * 0.16)
    }

    /// 图例问号按钮：点开算法说明弹层，把选股范围、打分公式等细节讲清楚。
    private var algorithmInfoButton: some View {
        Button {
            showAlgorithmInfo = true
        } label: {
            Image(systemName: "questionmark.circle")
                .font(.system(size: 15))
                .foregroundColor(Theme.textSecondary)
        }
        .accessibilityLabel(L("算法说明"))
        .sheet(isPresented: $showAlgorithmInfo) { algorithmInfoSheet }
    }

    /// 算法说明弹层：气泡视觉编码 + 扫描范围来源 + 上榜打分公式，对应后端
    /// app/services/signal_radar/{service.py, constituents.py, universe.py} 的实际口径。
    private var algorithmInfoSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    infoSection(L("气泡多久更新一次"), updateScheduleLines)
                    infoSection(L("气泡怎么看"), [
                        L("颜色：红=买点，绿=卖点；深浅=信号强弱（弱/中/强），越强越深，与详情页同一套判定。"),
                        L("大小：买卖点类型，一类最小、三类最大——越往后确认程度越高。"),
                        L("位置：越靠中心信号越新，由内向外依次摆开、互不重叠，画不下的点「查看全部」看。美股可在顶部「行业」里选一个行业，雷达只显示该行业的信号。"),
                        L("角标：「共振」= 日线方向与30分钟一致；「新」= 当日新出现的信号。"),
                    ])
                    infoSection(L("为什么点进详情页可能对不上"), [
                        L("气泡是最近一次全量扫描那一刻的快照（历史日期下方会标出算出时刻），不是实时数据；点进详情页是用当下最新K线重新跑一遍缠论。"),
                        L("缠论的笔和买卖点在最新几根K线上本身是临时性的，后续新K线一出现，原来某天的信号可能被延伸、改写甚至判定失效——这是分析方法的特性，不是数据错误。"),
                        L("越靠近「今天」的气泡越可能受影响；对某个信号有疑问，以点进详情页当下重新算出的结构为准。"),
                        L("气泡日期是信号出现那天；详情页图上的标记画在所属笔的极值 K 线，通常在出现日左侧几根，展开该买卖点可看到两个日期。"),
                    ])
                    infoSection(L("扫描范围怎么定"), [
                        L("每个市场提供「科技指数」（默认）和「大盘宽基」两套可切换范围，如美股的纳斯达克100 / 标普500。"),
                        L("成分股优先实时拉取官方/交易所数据源，取不到或数量不足时自动回退到内置清单，保证随时有得扫。"),
                    ])
                    infoSection(L("雷达上显示哪些信号"), rankingInfoLines)
                    Text(L("雷达只陈列按缠论规则得出的事实，不打分、不排名、不按基本面筛选；强弱与确认状态的判定与详情页完全一致，只是气泡取的是某一次扫描的快照。"))
                        .font(.footnote)
                        .foregroundColor(Theme.textSecondary)
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("算法说明"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("完成")) { showAlgorithmInfo = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    /// 说明弹层里的一个分组：标题 + 若干条目，条目前带圆点。
    /// 「气泡多久更新一次」：本次数据的实际计算时刻 + 调度规则。时刻与后端调度同源：
    /// 全量重扫 = 各市场收盘窗口末端 + 45 分钟（app/services/signal_radar/scheduler.py
    /// `_POST_CLOSE_BUFFER_MINUTES`、service.py `_SESSIONS_UTC`），按手机时区换算显示；
    /// 共振标记盘中每 30 分钟刷新（SIGNAL_RADAR_SUB_LEVEL_REFRESH_SECONDS）。
    private var updateScheduleLines: [String] {
        var lines: [String] = []
        if let computed = SignalRadarView.localStamp(vm.response?.computedAt) {
            if let sub = SignalRadarView.localStamp(vm.response?.subLevelAsOf) {
                lines.append(L("当前数据：%@ 全量计算，共振标记 %@ 更新。", computed, sub))
            } else {
                lines.append(L("当前数据：%@ 全量计算。", computed))
            }
        }
        lines.append(L("全量重扫：每个交易日收盘后约 45 分钟重算全部气泡（等行情源发布当天日线），按你的时区约为 美股 %@、A股 %@、港股 %@。盘中当天日线还没定型，不做全量重扫。",
                       SignalRadarView.localClock(utcHour: 22, minute: 15),
                       SignalRadarView.localClock(utcHour: 8, minute: 15),
                       SignalRadarView.localClock(utcHour: 9, minute: 15)))
        lines.append(L("盘中：每 30 分钟刷新一次最新一天的「共振」标记（日线方向 × 30 分钟买卖点），气泡位置和大小不变。"))
        lines.append(L("自动补算：服务重启后会先补扫一轮；数据过旧时，你打开本页也会在后台重算，期间先显示上一次的结果。"))
        lines.append(L("点进详情页是当下实时计算（不用缓存），盘中与气泡快照可能有出入，以详情页为准。"))
        return lines
    }

    /// UTC 时刻 → 手机本地时区的 HH:mm（全量重扫时刻按市场收盘写死在后端，这里只做换算）。
    static func localClock(utcHour: Int, minute: Int) -> String {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let date = utc.date(bySettingHour: utcHour, minute: minute, second: 0, of: Date()) ?? Date()
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }

    /// ISO8601 时间戳 → 本地「M/d HH:mm」，解析不了返回 nil。
    static func localStamp(_ iso: String?) -> String? {
        guard let iso, !iso.isEmpty, let date = ISO8601DateFormatter().date(from: iso) else { return nil }
        let f = DateFormatter()
        f.dateFormat = "M/d HH:mm"
        return f.string(from: date)
    }

    /// 「雷达上显示哪些信号」（App 固定严格口径：只显示已走完的笔上的买卖点，最后一笔上的只计「待确认」个数）。
    private var rankingInfoLines: [String] {
        [
            L("所选指数全部成分股都跑一遍缠论，某天在场的信号全部列出，按出现时间从新到旧，不打分、不截取前几名。"),
            L("在场：信号出现后 5 个交易日内（周末、休市不算），且收盘价没有跌破买点价位（卖点：涨破）；走坏当天起移出雷达，详情页仍显示该买卖点。"),
            L("只显示已成立的买卖点：所在的笔已经走完，并且下一笔也走完了才算，所以会比价格转折晚几天出现。最后一笔还在走时出现的只算「待确认」，在雷达上方显示个数，不画进雷达。"),
            L("基本面评级只标在气泡上，不参与筛选；画不下的气泡点「查看全部」可看全部。"),
        ]
    }

    private func infoSection(_ title: String, _ lines: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
            ForEach(lines, id: \.self) { line in
                HStack(alignment: .top, spacing: 6) {
                    Text("•").foregroundColor(Theme.textSecondary)
                    Text(line).font(.system(size: 13)).foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    // MARK: - 免责声明

    /// 压缩版免责声明，钉在页面最底部；完整版在「我的」页（App Store 要求必须可见）。
    private var compactDisclaimer: some View {
        Text(L("按缠论规则识别，仅为孤立观测，不构成投资建议。"))
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }

    // MARK: - 日期轨（底部横滑）

    private var dateRail: some View {
        VStack(spacing: 6) {
            HStack {
                Text(L("选择日期")).font(.caption).foregroundColor(Theme.textSecondary)
                Spacer()
                Text(L("← 左右滑动 →")).font(.caption2).foregroundColor(Theme.textSecondary)
            }
            ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    // 日期轨只摆最近 2 周（10 个交易日）的格子，够用又不用滑很远；
                    // 再往前的历史走"更多"里的日期选择器（范围覆盖后端返回的全部
                    // 天数，即近 1 个月），不用把几十个格子都塞进这条横滑条。
                    ForEach(Array(vm.days.prefix(SignalRadarView.visibleDayChipCount).enumerated()), id: \.element.id) { idx, day in
                        dayChip(day, index: idx).id(day.id)
                    }
                    moreDateChip.id(Self.moreChipID)
                }
                .padding(.horizontal, 2)
                .padding(.top, demoBadgeInset)
            }
            // 选中的日期默认滚到可见：未订阅时选中的是免费预览日（上个月 1 号，在轨道最右端），
            // 不滚过去就得手动滑；跳到 10 个交易日之前的某天时则对准最后那格（高亮的「更多」）。
            .onAppear { scrollToSelectedDay(proxy, animated: false) }
            .onChange(of: vm.baseSelectedDay?.id) { _, _ in scrollToSelectedDay(proxy, animated: true) }
            .onChange(of: vm.days.count) { _, _ in scrollToSelectedDay(proxy, animated: false) }
            }
        }
        .sheet(isPresented: $showDatePicker) { datePickerSheet }
    }

    private static let moreChipID = "radar-date-more-chip"

    /// 把选中日的格子滚到日期轨中间；等一帧让格子先完成布局再滚，否则初次进入时目标还没摆好。
    private func scrollToSelectedDay(_ proxy: ScrollViewProxy, animated: Bool) {
        guard let day = vm.baseSelectedDay else { return }
        let outside = vm.selectedDayIndex >= SignalRadarView.visibleDayChipCount
        let target: AnyHashable = outside ? Self.moreChipID : day.id
        DispatchQueue.main.async {
            if animated {
                withAnimation(.easeInOut(duration: 0.25)) { proxy.scrollTo(target, anchor: .center) }
            } else {
                proxy.scrollTo(target, anchor: .center)
            }
        }
    }

    /// 有「示例」标签时日期轨顶部多留的空间：标签骑在格子上沿外侧，
    /// 不留余量会被横向 ScrollView 的边界裁掉半截。
    private var demoBadgeInset: CGFloat {
        !store.isPremium && vm.unlockedDayDate != nil ? 8 : 0
    }

    /// 日期轨最后一格：打开日期选择器，可以直接跳到某一天（不用一格格滑）。
    private var moreDateChip: some View {
        // 当前选中日不在可见日期轨范围内——比如通过日期选择器跳到 10 个交易日
        // 之前的某天——时，这一格改用高亮态展示该日期本身，而不是
        // 灰底静态的「更多」，否则整条日期轨会一格都不高亮，看起来像没选中任何一天。
        let selectedOutsideVisible = vm.selectedDayIndex >= SignalRadarView.visibleDayChipCount
            && vm.days.indices.contains(vm.selectedDayIndex)
        return Button {
            pickedDate = SignalRadarView.parser.date(from: vm.selectedDay?.date ?? "") ?? Date()
            showDatePicker = true
        } label: {
            VStack(spacing: 3) {
                if selectedOutsideVisible, let day = vm.selectedDay {
                    Text(SignalRadarView.dayLabel(day.date))
                        .font(.system(size: 9)).foregroundColor(.white.opacity(0.85))
                    Text(SignalRadarView.monthDay(day.date))
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .foregroundColor(.white)
                } else {
                    Image(systemName: "calendar")
                        .font(.system(size: 14))
                        .foregroundColor(Theme.accent)
                    Text(L("更多")).font(.system(size: 11)).foregroundColor(Theme.accent)
                }
            }
            .frame(width: 56)
            .padding(.vertical, selectedOutsideVisible ? 8 : 12)
            .background(selectedOutsideVisible ? Theme.accent : Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(selectedOutsideVisible ? Theme.accent : Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    /// 日期选择器弹层：范围限定在 vm.days 覆盖的区间内，选完自动跳到最接近的交易日
    /// （周末/假日没有数据，落在这些天上就近取最接近的那个交易日）。
    private var datePickerSheet: some View {
        let dates = vm.days.compactMap { SignalRadarView.parser.date(from: $0.date) }
        let range: ClosedRange<Date> = {
            guard let lo = dates.min(), let hi = dates.max() else {
                let now = Date()
                return now...now
            }
            return lo...hi
        }()
        return NavigationStack {
            VStack {
                DatePicker(
                    L("选择日期"), selection: $pickedDate, in: range, displayedComponents: .date
                )
                .datePickerStyle(.graphical)
                .tint(Theme.accent)
                .padding()
                Spacer()
            }
            .background(Theme.background)
            .navigationTitle(L("选择日期"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("确定")) {
                        jumpToNearestDay(pickedDate)
                        showDatePicker = false
                    }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button(L("取消")) { showDatePicker = false }
                }
            }
        }
    }

    /// 挑一个日期 → 跳到 vm.days 里日期最接近的那个交易日（选中周末/假日时兜底）。
    private func jumpToNearestDay(_ date: Date) {
        guard !vm.days.isEmpty else { return }
        let target = SignalRadarView.parser.string(from: date)
        var bestIndex = 0
        var bestDiff = Int.max
        for (idx, day) in vm.days.enumerated() {
            let diff = SignalRadarView.absDayDiff(day.date, target)
            if day.date == target {
                bestIndex = idx
                break
            }
            if diff < bestDiff {
                bestDiff = diff
                bestIndex = idx
            }
        }
        selectDay(bestIndex)
    }

    /// 日期轨/日期选择器切某一天的唯一入口：未订阅会员时只有免费预览那天
    /// （vm.unlockedDayDate）能真的切过去，点其它天弹付费墙——雷达图本身跟会员
    /// 一模一样，只是这一层门禁不同，不是另起一套「示例」界面。
    private func selectDay(_ index: Int) {
        let unlocked = store.isPremium
            || (vm.days.indices.contains(index) && vm.days[index].date == vm.unlockedDayDate)
        if unlocked {
            vm.selectDay(index)
        } else {
            showPaywall = true
        }
    }

    private func dayChip(_ day: RadarDay, index: Int) -> some View {
        let active = index == min(max(vm.selectedDayIndex, 0), vm.days.count - 1)
        // 当天新出现的信号（而非从更早的日子延续下来）：气泡场里标"新"的同一批，
        // 在日期轨上也提前露个头，不用一天天点过去找。
        let hasNew = day.signals.contains { $0.date == day.date }
        // 未订阅时的免费预览日（上个月 1 号）：标「示例」，说明这天是给你试看的样例，
        // 不是雷达的最新结果。会员没有这一天，也就不会出现这个标记。
        let isDemo = !store.isPremium && day.date == vm.unlockedDayDate
        return Button {
            selectDay(index)
        } label: {
            VStack(spacing: 3) {
                // 「今日」只在这格确实是今天时才显示——数据源有延迟时最新一格可能是
                // 前一两个交易日，硬把第一格标成「今日」会让人以为 App 认死了今天是那天。
                Text(SignalRadarView.dayLabel(day.date))
                    .font(.system(size: 9))
                    .foregroundColor(active ? .white.opacity(0.85) : Theme.textSecondary)
                Text(SignalRadarView.monthDay(day.date))
                    .font(.system(size: 13, weight: .bold, design: .monospaced))
                    .foregroundColor(active ? .white : Theme.textPrimary)
            }
            .frame(width: 56)
            .padding(.vertical, 8)
            .background(active ? Theme.accent : Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(active ? Theme.accent : Theme.border, lineWidth: 1))
            // 「示例」骑在格子上沿外侧，不占格子内部空间；日期轨顶部留了余量
            // （见 dateRail 的 demoBadgeInset），不会被横向 ScrollView 裁掉。
            .overlay(alignment: .top) {
                if isDemo {
                    Text(L("示例"))
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(Theme.segment)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Theme.background, in: Capsule())
                        .overlay(Capsule().stroke(Theme.segment.opacity(0.7), lineWidth: 0.8))
                        .offset(y: -7)
                }
            }
            .overlay(alignment: .topTrailing) {
                if hasNew {
                    Circle()
                        .fill(Theme.accent)
                        .frame(width: 7, height: 7)
                        .overlay(Circle().stroke(Theme.background, lineWidth: 1.5))
                        .offset(x: 2, y: -2)
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: - 状态视图

    private var scanningView: some View {
        // 扫描范围是选定市场的代表性成分股（如纳斯达克100/科创50/恒生科技），
        // 不是"全市场"——文案得说实话，否则用户会以为在扫几千只股票。
        // response 在还没收到过任何回复（含 generating 态）之前是 nil，这时还
        // 不知道具体扫的是哪个 ETF，退回市场名兜底。
        let scope = currentUniverseName.isEmpty ? vm.market.title : currentUniverseName
        // 市场 / 指数选择器在页面顶部的分段条里（MarketHeader），扫描/计算期间用户都能随时切回已算好的指数，不被困住。
        return ZStack(alignment: .topLeading) {
            VStack(spacing: 12) {
                ProgressView().tint(Theme.accent)
                Text(L("正在扫描「%@」成分股…", scope))
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                Text(L("首次扫描较慢，稍候即可看到每日买卖点"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// 轮询用尽但后端仍在算（大盘首次全量扫描较久）：不干等转圈，给个明确交代 + 重试。
    /// 后台扫描会继续跑完并写缓存，点重试大概率直接命中。
    private var computingView: some View {
        let scope = currentUniverseName.isEmpty ? vm.market.title : currentUniverseName
        // 顶部保留切换器：正算大盘时用户可随时切回已算好的（缓存命中）指数，不被困住。
        return ZStack(alignment: .topLeading) {
            VStack(spacing: 12) {
                Image(systemName: "hourglass")
                    .font(.largeTitle).foregroundColor(Theme.textSecondary)
                Text(L("「%@」首次计算较久", scope))
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                Text(L("大盘成分较多，已在后台计算，稍后点重试即可查看"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.center).padding(.horizontal, 40)
                Button(L("重试")) { Task { await vm.load() } }
                    .buttonStyle(.borderedProminent).tint(Theme.accent)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity).padding()
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.largeTitle).foregroundColor(Theme.textSecondary)
            Text(message).font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button(L("重试")) { Task { await vm.load() } }
                .buttonStyle(.borderedProminent).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity).padding()
    }

    private var emptyView: some View {
        // 顶部保留股票池切换器：切到「自选」但自选为空时，能直接切回别的指数
        let emptyWatchlist = vm.activeUniverseKey == RadarUniverse.watchlistKey
            && (vm.response?.universeSize ?? 0) == 0
        return ZStack(alignment: .topLeading) {
            VStack(spacing: 12) {
                Image(systemName: emptyWatchlist ? "star" : "dot.radiowaves.left.and.right")
                    .font(.largeTitle).foregroundColor(Theme.textSecondary)
                if emptyWatchlist {
                    Text(L("自选中暂无该市场的股票"))
                        .font(.subheadline).foregroundColor(Theme.textPrimary)
                    Text(L("在分析详情页点右上角 ☆ 加入自选"))
                        .font(.footnote).foregroundColor(Theme.textSecondary)
                } else {
                    Text(L("近期暂无买卖点信号"))
                        .font(.subheadline).foregroundColor(Theme.textPrimary)
                    Button(L("刷新")) { Task { await vm.refresh() } }
                        .buttonStyle(.bordered).tint(Theme.accent)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - 日期格式化

    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    static func monthDay(_ date: String) -> String {
        let parts = date.split(separator: "-")
        return parts.count >= 3 ? "\(parts[1])-\(parts[2])" : date
    }

    /// 日期轨格子的顶部标签：是今天就「今日」，否则按语言显示星期几。
    /// 用本地自然日比较（跟用户视角一致），数据延迟时最新一格会如实显示成周几，
    /// 而不是被硬标成「今日」。
    static func dayLabel(_ date: String) -> String {
        date == parser.string(from: Date()) ? L("今日") : weekday(date)
    }

    /// 星期几按当前界面语言本地化（中文「周一」/ 英文「Mon」），不再硬编码中文。
    static func weekday(_ date: String) -> String {
        guard let d = parser.date(from: date) else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: Localized.language().localeIdentifier)
        f.setLocalizedDateFormatFromTemplate("EEE")
        return f.string(from: d)
    }
}
