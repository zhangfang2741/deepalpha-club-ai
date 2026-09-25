import SwiftUI

/// 信号雷达 Tab —— 扫描各市场科技 ETF 成分股跑缠论，把每日买卖点前 12 只用气泡呈现。
///
/// 顶部市场选择与三地恐慌指数小卡片合二为一（PanicIndexStrip）：点哪张卡就切到
/// 哪个市场，不再单独放一条分段选择器。
///
/// 气泡编码（四个视觉维度对应四件不同的事，不再互相重复）：
/// - 颜色：方向（红=买点 / 绿=卖点）+ 深浅（信号强弱：越强越深，与详情页共用映射）；
/// - 大小：买卖点级别本身的确定性（一类最小 → 三类最大）——一类只是背驰迹象、
///   尚待验证，二类回踩不破中枢是初步确认，三类回踩完全不回中枢是最强确认；
/// - 边框：单条信号自身是否已被后续走势确认——虚线=未确认
///   （`signal.confirmed == false`），跟图表页「虚线=未确认」同一套语言。这是
///   「这一条信号有没有走完」的实时状态，跟大小编码的「这一类信号本身多可信」
///   是两件不同的事，不重复；
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
    @StateObject private var panicVM = PanicIndexViewModel()
    @EnvironmentObject private var orientation: AppOrientation

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
                    bubbleField
                        // 切换市场/刷新时：气泡清空（见 bubbleField），盖一道旋转的雷达扫描光束表示
                        // 正在扫描，扫完新气泡直接出现；布局不变，页面不跳动
                        .allowsHitTesting(!vm.isReloading)
                        .overlay {
                            if vm.isReloading {
                                RadarSweep()
                                    .allowsHitTesting(false)
                                    .transition(.opacity)
                            }
                        }
                        .animation(.easeInOut(duration: 0.3), value: vm.isReloading)
                    legend
                    dateRail
                    Spacer(minLength: 0)
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 10)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Theme.background)
            .navigationTitle(L("缠论信号"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { refreshButton }
            }
            .task { vm.onAppear() }
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
    private func openSymbol(_ symbol: String, name: String? = nil) {
        let end = SignalRadarView.parser.date(from: vm.response?.asOf ?? "") ?? Date()
        let start = Calendar.current.date(byAdding: .day, value: -270, to: end) ?? end
        chanVM.apply(
            // 名称为空（美股无中文名）时不传，详情页标题退回显示代码
            market: vm.market, symbol: symbol, name: (name?.isEmpty ?? true) ? nil : name,
            startDate: start, endDate: end, freq: "daily", warmupDays: 0)
        Task {
            await chanVM.runAnalysis()
            if chanVM.errorMessage == nil, chanVM.analysis != nil {
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

    // MARK: - 刷新

    /// 这页是固定气泡画布、不是可滚动列表，`.refreshable` 用不上，改用导航栏右上角
    /// 的刷新按钮触发强制重扫（refresh=true），把行情源新发布的日线拉进来。
    private var refreshButton: some View {
        Button {
            Task { await vm.refresh() }
        } label: {
            if vm.isLoading {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: "arrow.clockwise")
            }
        }
        .disabled(vm.isLoading)
        .accessibilityLabel(L("刷新"))
    }

    // MARK: - 说明行

    private var metaRow: some View {
        // 指数名称已移到雷达左上角的切换器里，这行只留日期 + 当日买卖点数，避免重复。
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let day = vm.selectedDay {
                Text(day.date)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                // 共振标记只在最新交易日出现、盘中每 30 分钟刷新：标出更新时刻，
                // 与点进详情看到的实时结论有出入时，用户知道差在时间上
                if day.id == vm.response?.days.first?.id,
                   day.signals.contains(where: { $0.isSubLevelResonance }),
                   let updated = vm.response?.subLevelUpdatedText {
                    Text(L("共振 %@ 更新", updated))
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

    private var bubbleField: some View {
        GeometryReader { geo in
            let w = Double(geo.size.width)
            let h = Double(geo.size.height)
            let base = min(w, h)
            // 参考环与气泡共用的内缩场半轴：椭圆填满画布，长边不再留大片空白。
            let (hRad, vRad) = SignalRadarView.fieldRadii(width: w, height: h)
            let dayDate = vm.selectedDay?.date ?? ""
            let signals = (vm.selectedDay?.signals ?? [])
                .sorted { $0.strength > $1.strength }
            let layouts = SignalRadarView.layoutBubbles(signals: signals, dayDate: dayDate, width: w, height: h)
            ZStack {
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

                if vm.isReloading {
                    // 刷新/切换市场中：清空气泡，只留参考环、光晕与扫描光束，扫完再淡入新气泡
                    EmptyView()
                } else if layouts.isEmpty {
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
                                depth: SignalRadarView.levelDepth(layout.signal.level)),
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
        .overlay(alignment: .topLeading) { universeSwitcher }
    }

    // MARK: - universe 切换器（雷达左上角）

    /// 当前 universe 展示名：优先从列表里按高亮键取（计算中 response 为 nil 时也有名字），
    /// 否则退回响应里的 etf_name。
    private var currentUniverseName: String {
        if let u = vm.universes.first(where: { $0.key == vm.activeUniverseKey }) {
            return u.displayName
        }
        if vm.activeUniverseKey == RadarUniverse.watchlistKey { return L("自选") }
        return vm.response?.etfName ?? ""
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

    /// 三个等距参考环：今天 1/3、3 天 2/3、1 周 1.0，与气泡同一套时间半径映射
    /// （RadarOrbitSpacing.timeRadius）。
    /// 用计算属性而非 static let：L() 依赖运行时语言设置，static let 只会算一次，
    /// 用户切换语言后文案不会跟着变。
    static var ringSpecs: [(scale: Double, label: String)] {
        [(1.0 / 3, L("今天")), (2.0 / 3, L("3天内")), (1.0, L("一周内"))]
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

    /// daysAgo → 时间档：0=今天、1=3天内、2=一周内（含更早，最多保留 7 天）。
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
    ///   横向」的方向（RadarOrbitSpacing.bestAngle）。半径不为避让而改变——不同轨道放不开时允许重叠，
    ///   否则「远近 = 时间」就不成立了。
    private static func layoutBubbles(
        signals: [RadarSignal], dayDate: String, width w: Double, height h: Double
    ) -> [BubbleLayout] {
        guard !signals.isEmpty else { return [] }
        let (hRad, vRad) = fieldRadii(width: w, height: h)
        // 椭圆轨道：相对半径 r（= 时间）对应横半轴 r·hRad、纵半轴 r·vRad；放不下时按平均半轴外扩
        let meanRadius = ((hRad * hRad + vRad * vRad) / 2).squareRoot()
        let center = (x: w / 2, y: h / 2)
        let scales = ringSpecs.map(\.scale)
        func age(_ s: RadarSignal) -> Int { daysAgo(from: s.date, to: dayDate) }
        let maxDiameter = max(1, min(w, h) - 2 * RadarBubbleMetrics.edgePadding)
        // 每次布局每个信号只测量一次，排序和避让都使用最终尺寸。
        let metrics = signals.map { signal in
            RadarBubbleMetrics(symbol: signal.symbol, name: signal.name,
                               baseDiameter: diameter(forStrength: signal.signalStrength) * ringSizeFactor(forDaysAgo: age(signal)),
                               maxDiameter: maxDiameter)
        }
        let sizedSignals = Array(zip(signals, metrics))
        let byDay = Dictionary(grouping: sizedSignals) { age($0.0) }
        var layouts: [BubbleLayout] = []
        var placed: [RadarOrbitSpacing.Placed] = []
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
                layouts.append(BubbleLayout(signal: sig, metrics: metrics, x: x, y: y,
                                            phase: Double(layouts.count) * 0.35, daysAgo: days))
            }
        }
        // 叠层：越接近查看日（daysAgo 越小）画得越晚，重叠时新的浮在上面
        layouts.sort { $0.daysAgo > $1.daysAgo }
        return layouts
    }

    /// 买卖点强弱 → 气泡直径：越强越大（弱 60 / 中 76 / 强 92），与详情页买卖点
    /// 「强/中/弱」同一口径（一类按背驰力度比、二三类按中枢级别 + 回踩余地），未知按中。
    /// 单条信号「有没有走完」用边框实/虚线表达（见 RadarBubble），不叠加到大小上。
    static func diameter(forStrength strength: String) -> Double {
        switch strength {
        case "strong": return 92
        case "weak": return 60
        default: return 76
        }
    }

    /// 买卖点类型 → 颜色深浅：一类最浅（只是背驰迹象、尚待验证）、二类居中（回踩不破
    /// 中枢，初步确认）、三类最深（回踩完全不回中枢，确认程度最高）。
    static func levelDepth(_ level: Int) -> Double {
        switch level {
        case 1: return 0.2
        case 2: return 0.55
        default: return 0.9
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

    /// 与详情页共用同一套渐变色（深浅含义在雷达上是买卖点类型）。
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
                Text(L("颜色=方向")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
            }
            HStack(spacing: 3) {
                sizeDot(diameter: SignalRadarView.diameter(forStrength: "weak"))
                sizeDot(diameter: SignalRadarView.diameter(forStrength: "strong"))
                Text(L("大小=强弱")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
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

    /// 图例里的强弱参考点：真实按 `diameter(forStrength:)` 等比缩小展示，不带文字标签
    /// （弱/中/强的说明移进算法说明弹层，这里只给一眼看出"有大有小"的直观印象）。
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
                    infoSection(L("气泡怎么看"), [
                        L("颜色：红=买点，绿=卖点；深浅=买卖点类型的确认程度，一类最浅、三类最深。"),
                        L("大小：买卖点自身强弱（弱/中/强），越强气泡越大，与详情页同一套判定。"),
                        L("位置：离中心越近代表信号越新，三个圈依次是今天、3天内、一周内。"),
                        L("边框：虚线表示这条信号还没被后续走势确认。"),
                        L("角标：「共振」= 日线方向与30分钟一致；「新」= 当日新出现的信号。"),
                    ])
                    infoSection(L("扫描范围怎么定"), [
                        L("每个市场提供「科技指数」（默认）和「大盘宽基」两套可切换范围，如美股的纳斯达克100 / 标普500。"),
                        L("成分股优先实时拉取官方/交易所数据源，取不到或数量不足时自动回退到内置清单，保证随时有得扫。"),
                    ])
                    infoSection(L("上榜排序怎么算"), [
                        L("综合分 = 35% 类型确定性 + 30% 强弱 + 35% 新鲜度，最新一天命中「共振」再额外加分。"),
                        L("类型确定性：一类 0.4（背驰迹象，待验证）、二类 0.7（回踩不破中枢）、三类 1.0（完全不回中枢，最强确认）。"),
                        L("新鲜度：当天最高，7 天后归零；超过 7 天没被更新信号覆盖的旧信号会自动退场。"),
                        L("每类买卖点先保底最多 2 个名额，其余按综合分从高到低补满，共取前 12 名。"),
                    ])
                    Text(L("以上口径与详情页强弱、确认状态完全一致。"))
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
            }
        }
        .sheet(isPresented: $showDatePicker) { datePickerSheet }
    }

    /// 日期轨最后一格：打开日期选择器，可以直接跳到某一天（不用一格格滑）。
    private var moreDateChip: some View {
        Button {
            pickedDate = SignalRadarView.parser.date(from: vm.selectedDay?.date ?? "") ?? Date()
            showDatePicker = true
        } label: {
            VStack(spacing: 3) {
                Image(systemName: "calendar")
                    .font(.system(size: 14))
                    .foregroundColor(Theme.accent)
                Text(L("更多")).font(.system(size: 11)).foregroundColor(Theme.accent)
            }
            .frame(width: 56)
            .padding(.vertical, 12)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
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
        vm.selectDay(bestIndex)
    }

    private func dayChip(_ day: RadarDay, index: Int) -> some View {
        let active = index == min(max(vm.selectedDayIndex, 0), vm.days.count - 1)
        // 当天新出现的信号（而非从更早的日子延续下来）：气泡场里标"新"的同一批，
        // 在日期轨上也提前露个头，不用一天天点过去找。
        let hasNew = day.signals.contains { $0.date == day.date }
        return Button {
            vm.selectDay(index)
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

/// 加载中的雷达扫描光束：一道扇形渐变绕场中心匀速旋转，像雷达在扫描。
/// 叠加（plusLighter）在气泡之上，不遮挡、不调暗原有内容。
struct RadarSweep: View {
    @State private var angle: Double = 0

    var body: some View {
        GeometryReader { geo in
            let side = hypot(geo.size.width, geo.size.height)
            AngularGradient(
                gradient: Gradient(stops: [
                    .init(color: Theme.accent.opacity(0.0), location: 0.0),
                    .init(color: Theme.accent.opacity(0.0), location: 0.80),
                    .init(color: Theme.accent.opacity(0.22), location: 0.97),
                    .init(color: Theme.accent.opacity(0.55), location: 1.0),
                ]),
                center: .center
            )
            .frame(width: side, height: side)
            .rotationEffect(.degrees(angle))
            .position(x: geo.size.width / 2, y: geo.size.height / 2)
            .blendMode(.plusLighter)
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .onAppear {
            withAnimation(.linear(duration: 1.6).repeatForever(autoreverses: false)) {
                angle = 360
            }
        }
    }
}
