import SwiftUI

/// 信号雷达 Tab —— 扫描各市场科技 ETF 成分股跑缠论，把每日买卖点前 10 只用气泡呈现。
///
/// 顶部市场选择与三地恐慌指数小卡片合二为一（PanicIndexStrip）：点哪张卡就切到
/// 哪个市场，不再单独放一条分段选择器。
///
/// 气泡编码（三个视觉维度对应三件不同的事，不再互相重复；纯实色气泡，
/// 不用边框表达确认状态——那是详情页里的事，见 RadarBubble）：
/// - 颜色：方向（红=买点 / 绿=卖点）+ 深浅（形态强弱：弱/中/强，与详情页买卖点
///   色块同一映射 SignalFormatting.strengthDepth），越强越深；
/// - 大小：买卖点类型（一类最小、二类居中、三类最大——一类只是背驰迹象、尚待验证，
///   三类回踩完全不回中枢，确认程度最高）；
/// - 居中程度：时间距离——当天信号位于中心，越早出现的信号越靠外；
///   后端会让一只股票的信号在被更新的信号覆盖前持续「在场」（见
///   app/services/signal_radar/service.py 的按日重建），所以翻看某一天时，
///   有的气泡是当天新出现的（右上角标"新"），有的是更早出现、一直有效到今天的。
/// 底部可横滑的日期轨手动选某一天，看当天信号。
/// 点气泡直接在本页自己的 NavigationStack 里 push 到缠论分析详情页——不经过
/// 分析 Tab 的条件页中转，右滑手势/返回按钮也就自然直接回到信号页。
struct SignalRadarView: View {
    /// 与分析 Tab 共享的缠论状态（同 MorningReportTabView），这样从信号页
    /// 分析过的标的，切到分析 Tab 时条件与结果也是同步的。
    @ObservedObject var chanVM: ChanViewModel

    @StateObject private var vm = SignalRadarViewModel()
    /// 叠在雷达左上角的指数切换按钮实测尺寸，气泡摆位时避开（见 layoutBubbles）。
    @State private var switcherSize: CGSize = .zero
    @StateObject private var panicVM = PanicIndexViewModel()
    @EnvironmentObject private var orientation: AppOrientation
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    /// 信号雷达图跟高级版完全是同一套 UI（同一个 vm），未订阅时唯一的区别：
    /// vm.days 最前面多一天「上个月 1 号」的真实快照（见 SignalRadarViewModel.demoDay），
    /// 默认停在这天；点日期轨上其它天会弹这个付费墙，而不是真的切过去——见 selectDay。
    @State private var showPaywall = false
    /// 免责声明：第一次查看非示例日的雷达图（即订阅高级版后的真实雷达）时弹出，
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

    var body: some View {
        NavigationStack {
            radarContent
            .background(Theme.background)
            .navigationTitle(L("缠论信号"))
            .navigationBarTitleDisplayMode(.inline)
            // 真实滚动窗口雷达对所有用户都拉（未订阅一样看得到市场卡片、图例、日期轨，
            // 跟高级版一模一样，见 radarContent）；市场切换时 .task(id:) 额外拉一次
            // 「上个月 1 号」免费预览快照，自动取消上一次未完成的请求、重新拉一次。
            .task { vm.onAppear() }
            .task(id: vm.demoKey) {
                if !store.isPremium { await vm.loadDemoDay() }
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
    /// 时存在）不需要；高级版没有示例日，所有日期都需要。
    private var needsConsent: Bool {
        guard !consent.hasAgreed, let day = vm.selectedDay else { return false }
        return day.date != vm.unlockedDayDate
    }

    /// 正文：市场卡片 + 雷达。跟高级版完全同一套 UI，未订阅时唯一的区别在 vm.days
    /// （最前面多一天免费预览）和 selectDay（点非解锁日弹付费墙）。非示例日未同意免责
    /// 声明时，气泡区换成锁定占位（consentLockedField）。
    private var radarContent: some View {
        VStack(spacing: 12) {
            PanicIndexStrip(radarVM: vm, panicVM: panicVM)

            if vm.isScanning {
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

    // MARK: - 免责声明

    /// 气泡区锁定占位：非示例日、未同意免责声明时代替气泡显示，可重新打开声明。
    private var consentLockedField: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 30)).foregroundColor(Theme.textSecondary)
            Text(L("查看信号雷达前，请阅读并同意免责声明"))
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
                    Text(L("信号雷达免责声明"))
                        .font(.headline).foregroundColor(Theme.textPrimary)
                }
                .frame(maxWidth: .infinity)

                Text(L("信号雷达基于公开行情数据，按缠论结构规则自动识别并汇总所选指数成分股的买卖点形态，供技术分析研究使用。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 10) {
                    consentPoint(L("本功能展示的内容均为算法生成的技术分析结果，不构成任何投资建议、证券推荐或买卖要约。"))
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
    /// 关键：让详情页与雷达完全同口径。雷达是在 today-270 ~ today 的日线上跑缠论
    /// （全序列、不额外加 warmup）。这里传 end=雷达数据日(as_of)、start=end-270 天、
    /// warmupDays=0：详情接口不再前补 warmup，取到的正是 today-270 ~ today 这同一段
    /// K 线，且整段都可见——买卖点集合与雷达一致（连更早、超过 90 天的买卖点也照常显示，
    /// 不会因可见窗口太窄被挡掉）。270 = 雷达的 warmup(180) + window*2(90)，见后端
    /// signal_radar/service.py。
    ///
    /// 未订阅高级版时（含点开免费预览那一天）这次分析跟分析 Tab 一样走每日免费额度
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
        // 指数名称已移到雷达左上角的切换器里，这行只留日期 + 当日买卖点数，避免重复。
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
                Text(L("%lld 买点", day.buyCount))
                    .font(.caption.bold()).foregroundColor(Theme.up)
                Text("·").font(.caption).foregroundColor(Theme.textSecondary)
                Text(L("%lld 卖点", day.sellCount))
                    .font(.caption.bold()).foregroundColor(Theme.down)
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

        // 同心参考环：越外越淡，呼应同一套"近实远虚"的纵深语言；环上直接标出
        // 大致时间跨度，不用再靠单独一行说明文字解释三个圈是什么意思。
        ForEach(Array(SignalRadarView.ringSpecs.enumerated()), id: \.offset) { idx, spec in
            // 正圆：离中心的距离 = 时间，各方向一致
            // 横向椭圆：左右宽、上下窄，与气泡摆位同一套半轴
            let rx = hRad * spec.scale
            let ry = vRad * spec.scale
            Ellipse()
                .stroke(Theme.textSecondary.opacity(0.16 - Double(idx) * 0.045),
                        style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                .frame(width: CGFloat(rx * 2), height: CGFloat(ry * 2))
                .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
            Text(spec.label)
                .font(.system(size: 8))
                .foregroundColor(Theme.textSecondary.opacity(0.55))
                .position(x: CGFloat(w / 2), y: CGFloat(h / 2) - CGFloat(ry) + 8)
        }
    }

    private var bubbleField: some View {
        GeometryReader { geo in
            let w = Double(geo.size.width)
            let h = Double(geo.size.height)
            let dayDate = vm.selectedDay?.date ?? ""
            let signals = (vm.selectedDay?.signals ?? [])
                .sorted { $0.strength > $1.strength }
            let layouts = SignalRadarView.layoutBubbles(
                signals: signals, dayDate: dayDate, width: w, height: h,
                avoid: switcherSize == .zero ? [] : [.init(x: 0, y: 0, width: Double(switcherSize.width),
                                                            height: Double(switcherSize.height))])
            ZStack {
                fieldDecoration(width: w, height: h)

                if layouts.isEmpty {
                    Text(L("当日无买卖点信号"))
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                } else {
                    ForEach(layouts) { layout in
                        RadarBubble(
                            signal: layout.signal,
                            metrics: layout.metrics,
                            baseX: CGFloat(layout.x),
                            baseY: CGFloat(layout.y),
                            phase: layout.phase,
                            color: SignalRadarView.bubbleColor(
                                side: layout.signal.side,
                                depth: SignalFormatting.strengthDepth(layout.signal.signalStrength)),
                            isNew: layout.signal.date == dayDate,
                            onOpen: { openSymbol(layout.signal.symbol, name: layout.signal.name) }
                        )
                        // 气泡任何时候都不做透明处理：刷新完直接出现，不淡入
                        .transition(.identity)
                    }
                }
            }
        }
        // 横向椭圆：画布宽高比约 1.3 : 1，腾出的纵向空间留给下方图例与日期轨
        .frame(maxWidth: .infinity)
        .aspectRatio(SignalRadarView.fieldAspect, contentMode: .fit)
        .background(
            RadialGradient(
                colors: [Color(hex: 0x131A26), Theme.background],
                center: .center, startRadius: 6, endRadius: 280
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(alignment: .topLeading) {
            // 实测按钮大小（随指数名称长短变化），气泡摆位时当作禁区避开
            universeSwitcher
                .onGeometryChange(for: CGSize.self) { $0.size } action: { switcherSize = $0 }
        }
    }

    // MARK: - universe 切换器（雷达左上角）

    /// 当前 universe 展示名：优先从列表里按高亮键取（计算中 response 为 nil 时也有名字），
    /// 否则退回响应里的 etf_name。
    private var currentUniverseName: String {
        if let u = vm.universes.first(where: { $0.key == vm.activeUniverseKey }) {
            return u.displayName
        }
        if vm.activeUniverseKey == RadarUniverse.watchlistKey { return L("自选") }
        // 切市场时 response 暂时还是上一个市场的（保留旧内容防跳动），它的名称不能拿来用，
        // 否则选了 A 股却显示「正在扫描纳斯达克100」。还没拿到过这个市场的列表时用默认
        // 指数名兜底，直接显示「科创50」，不先闪一下「A 股」。
        if let response = vm.response, response.market == vm.market.rawValue { return response.etfName }
        if vm.activeUniverseKey == SignalRadarViewModel.defaultUniverseKeys[vm.market] {
            return SignalRadarViewModel.defaultUniverseNames[vm.market] ?? ""
        }
        return ""
    }

    /// 雷达左上角的 universe 切换器：科技窄基 ↔ 大盘宽基（如 恒生科技 ↔ 恒生指数）。
    /// 只有该市场确实有多个 universe 时才是可点的下拉；否则退化成一个静态名牌，
    /// 保证名称永远显示（metaRow 已不再重复显示名称）。
    @ViewBuilder
    private var universeSwitcher: some View {
        if vm.universes.count > 1 {
            Menu {
                ForEach(vm.universes) { u in
                    Button {
                        vm.switchUniverse(u.key)
                    } label: {
                        if u.key == vm.activeUniverseKey {
                            Label(u.displayName, systemImage: "checkmark")
                        } else {
                            Text(u.displayName)
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Text(currentUniverseName).font(.system(size: 12, weight: .semibold))
                    Image(systemName: "chevron.down").font(.system(size: 9, weight: .semibold))
                }
                .foregroundColor(Theme.textPrimary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Theme.surface.opacity(0.92))
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Theme.border, lineWidth: 1))
            }
            .padding(10)
            .accessibilityLabel(L("切换指数范围"))
        } else if !currentUniverseName.isEmpty {
            Text(currentUniverseName)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.textPrimary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Theme.surface.opacity(0.92))
                .clipShape(Capsule())
                .padding(10)
        }
    }

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
        [(1.0 / 3, L("当日")), (2.0 / 3, L("3天内")), (1.0, L("一周内"))]
    }

    /// 场边距：最外环（scale 1.0）到容器四边留出的空白，给气泡的阴影 + 右上角「新」
    /// 角标 + 拖拽放大留余量。以前最外环半径直接取 min(w,h)/2，环线正好压在容器边上，
    /// 落在最外环、角度又指向边缘的气泡（尤其是那颗被推到远端的孤立卖点）就会被
    /// 圆角容器裁掉一半。现在把「场半径」整体内缩这个边距，环线和气泡一起内移。
    static let fieldInset: Double = 18
    /// 雷达画布宽高比与椭圆纵/横半轴比。图例精简成一行 + 问号弹层后空出的纵向空间
    /// 让给了画布本身：宽高比从 1.3 收到 1.1（画布更高），ellipseRatio 从 0.72 提到
    /// 0.9——不然只把画布拉高、椭圆纵向半轴仍卡在旧比例上限，新增的高度只会变成
    /// 椭圆上下的空白，而不是让椭圆本身跟着变大。常见手机宽度下 0.9 已经让
    /// `fieldRadii` 里 `min(h/2-fieldInset, hRad*ellipseRatio)` 的瓶颈从
    /// ellipseRatio 切回画布高度本身，椭圆基本吃满新增的纵向空间。
    static let fieldAspect: CGFloat = 1.1
    static let ellipseRatio: Double = 0.9

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

    /// 允许两个气泡边缘重叠「较小直径 × 此比例」。0.2 时重叠最深处离被盖气泡中心仍有
    /// 约 0.6 个半径，中间的代码和名称不会被盖住；再大就开始压字。
    static let bubbleOverlapRatio: Double = 0.2

    /// 买卖点类型 → 气泡直径：一类 78 / 二类 90 / 三类 102。一类只是背驰迹象、尚待验证，
    /// 三类回踩完全不回中枢、确认程度最高，越确认越大。三档面积比原先 (70/88/108) 收窄
    /// 到约 1.7 倍（原先约 2.4 倍）：三类仍最大，但不至于让一类显得过小、三类过分抢眼。
    static func diameter(forLevel level: Int) -> Double {
        switch level {
        case 1: return 78
        case 2: return 90
        default: return 102
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

    /// 与详情页共用同一套渐变色（深浅 = 形态强弱，两边同一口径）。
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
                Text(L("深浅=形态强弱")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            HStack(spacing: 3) {
                sizeDot(diameter: SignalRadarView.diameter(forLevel: 1))
                sizeDot(diameter: SignalRadarView.diameter(forLevel: 3))
                Text(L("大小=一二三类")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            HStack(spacing: 4) {
                legendBadge(L("新"), color: Theme.segment)
                Text(L("标签=状态")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            Spacer(minLength: 4)
            algorithmInfoButton
        }
    }

    /// 图例里的角标样例：与气泡上的「共振」「新」同一样式。
    private func legendBadge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 8, weight: .bold))
            .foregroundColor(.white)
            .padding(.horizontal, 4)
            .padding(.vertical, 1.5)
            .background(color, in: Capsule())
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
                        L("颜色：红=买点，绿=卖点；深浅=形态强弱（弱/中/强），越强越深，与详情页同一套判定。"),
                        L("大小：买卖点类型，一类最小、三类最大——越往后确认程度越高。"),
                        L("位置：大致越靠中心信号越新（按信号出现后的交易日数，周末不算），三个圈依次是今天、3个交易日内、一周内；气泡太挤时会自动推开。"),
                        L("角标：「共振」= 日线方向与30分钟一致；「新」= 当日新出现的信号。"),
                    ])
                    infoSection(L("为什么点进详情页可能对不上"), [
                        L("气泡是最近一次全量扫描那一刻的快照（历史日期下方会标出算出时刻），不是实时数据；点进详情页是用当下最新K线重新跑一遍缠论。"),
                        L("缠论的笔和买卖点在最新几根K线上本身是临时性的，后续新K线一出现，原来某天的信号可能被延伸、改写甚至判定失效——这是分析方法的特性，不是数据错误。"),
                        L("越靠近「今天」的气泡越可能受影响；对某个信号有疑问，以点进详情页当下重新算出的结构为准。"),
                    ])
                    infoSection(L("扫描范围怎么定"), [
                        L("每个市场提供「科技指数」（默认）和「大盘宽基」两套可切换范围，如美股的纳斯达克100 / 标普500。"),
                        L("成分股优先实时拉取官方/交易所数据源，取不到或数量不足时自动回退到内置清单，保证随时有得扫。"),
                    ])
                    infoSection(L("上榜排序怎么算"), [
                        L("综合分 = 35% 类型确定性 + 30% 强弱 + 35% 新鲜度，最新一天命中「共振」再额外加分。"),
                        L("类型确定性：一类 0.4（背驰迹象，待验证）、二类 0.7（回踩不破中枢）、三类 1.0（完全不回中枢，最强确认）。"),
                        L("新鲜度：按信号出现后的交易日数算（周末、休市不算），当天最高，5 个交易日（一周）后归零并退场。"),
                        L("未确认的信号（落在最后一笔上的提前预判）：类型确定性和强弱两部分打 6 折，新鲜度不打折。"),
                        L("价格走坏即退场：信号出现后，收盘价跌破买点价位（卖点：涨破）就判定失效，当天起不再上榜。"),
                        L("每类买卖点先保底最多 2 个名额，其余按综合分从高到低补满，共取前 10 名。"),
                    ])
                    Text(L("以上打分口径与详情页强弱、确认状态判定完全一致，只是气泡取的是某一次扫描的快照。"))
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
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
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
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    // 日期轨只摆最近 2 周（10 个交易日）的格子，够用又不用滑很远；
                    // 再往前的历史走"更多"里的日期选择器（范围覆盖后端返回的全部
                    // 天数，即近 1 个月），不用把几十个格子都塞进这条横滑条。
                    ForEach(Array(vm.days.prefix(SignalRadarView.visibleDayChipCount).enumerated()), id: \.element.id) { idx, day in
                        dayChip(day, index: idx)
                    }
                    moreDateChip
                }
                .padding(.horizontal, 2)
                .padding(.top, demoBadgeInset)
            }
        }
        .sheet(isPresented: $showDatePicker) { datePickerSheet }
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

    /// 日期轨/日期选择器切某一天的唯一入口：未订阅高级版时只有免费预览那天
    /// （vm.unlockedDayDate）能真的切过去，点其它天弹付费墙——雷达图本身跟高级版
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
        // 不是雷达的最新结果。高级版没有这一天，也就不会出现这个标记。
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
        // 顶部保留切换器：扫描/计算期间用户都能随时切回已算好的指数，不被困住。
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
            universeSwitcher
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
            universeSwitcher
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
            universeSwitcher
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
