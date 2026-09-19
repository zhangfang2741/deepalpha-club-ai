import SwiftUI

/// 信号雷达 Tab —— 扫描各市场科技 ETF 成分股跑缠论，把每日买卖点前 10 只用气泡呈现。
///
/// 顶部市场选择与三地恐慌指数小卡片合二为一（PanicIndexStrip）：点哪张卡就切到
/// 哪个市场，不再单独放一条分段选择器。
///
/// 气泡编码（四个视觉维度对应四件不同的事，不再互相重复）：
/// - 颜色：方向（红=买点 / 绿=卖点）+ 深浅（形态技术面强弱）；
/// - 大小：买卖点级别的潜在行情空间（一类最大 → 三类最小）——一类能吃到从底部
///   开始的整段反转，三类只剩突破后的延续段；
/// - 边框：确定性——虚线=未确认（`signal.confirmed == false`），跟图表页
///   「虚线=未确认」同一套语言。级别（一/二/三类）本身隐含的"确定性"不再叠加
///   到大小上：那会跟"深浅=强弱"读成同一件事，两个独立维度混成了一个；
/// - 居中程度：时间距离——信号是哪天出现的离当前查看的这天越近，越靠中心；
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

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                PanicIndexStrip(radarVM: vm, panicVM: panicVM)

                if vm.isScanning {
                    scanningView
                } else if let error = vm.errorMessage {
                    errorView(error)
                } else if vm.days.isEmpty {
                    emptyView
                } else {
                    metaRow
                    bubbleField
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
    private func openSymbol(_ symbol: String) {
        chanVM.apply(market: vm.market, symbol: symbol)
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

    // MARK: - 说明行

    private var metaRow: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(vm.response?.etfName ?? "")
                .font(.subheadline.bold())
                .foregroundColor(Theme.textPrimary)
            if let day = vm.selectedDay {
                Text("· \(day.date)")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
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
            // 参考环与气泡共用的内缩场半径：最外环内缩 fieldInset，不贴容器边。
            let fieldRadius = SignalRadarView.fieldRadius(width: w, height: h)
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
                    let ringR = fieldRadius * spec.scale
                    Circle()
                        .stroke(Theme.textSecondary.opacity(0.16 - Double(idx) * 0.045),
                                style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        .frame(width: CGFloat(ringR * 2), height: CGFloat(ringR * 2))
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                    Text(spec.label)
                        .font(.system(size: 8))
                        .foregroundColor(Theme.textSecondary.opacity(0.55))
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2) - CGFloat(ringR) + 8)
                }

                if layouts.isEmpty {
                    Text(L("当日无买卖点信号"))
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                } else {
                    ForEach(layouts) { layout in
                        let da = SignalRadarView.daysAgo(from: layout.signal.date, to: dayDate)
                        RadarBubble(
                            signal: layout.signal,
                            diameter: CGFloat(layout.diameter),
                            baseX: CGFloat(layout.x),
                            baseY: CGFloat(layout.y),
                            phase: layout.phase,
                            color: SignalRadarView.bubbleColor(side: layout.signal.side, strength: layout.signal.strength),
                            fade: SignalRadarView.ringOpacity(forDaysAgo: da),
                            isNew: layout.signal.date == dayDate,
                            onOpen: { openSymbol(layout.signal.symbol) }
                        )
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .frame(minHeight: 320)
        .background(
            RadialGradient(
                colors: [Color(hex: 0x131A26), Theme.background],
                center: .center, startRadius: 6, endRadius: 280
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    /// 单个气泡的最终布局：先按「离查看日多少天」落到三个同心环之一（对应场里画的
    /// 三条参考虚线圈）+ 向日葵螺旋角度定初始位置，再跑一轮碰撞松弛
    /// （resolveOverlaps）把挤在一起的气泡推开，保证点得到。
    private struct BubbleLayout: Identifiable {
        let signal: RadarSignal
        let diameter: Double
        var x: Double
        var y: Double
        let phase: Double
        let daysAgo: Int
        var id: String { signal.id }
    }

    /// 三档环的半径比例 + 环上标注的大致时间跨度文案，参考圈和气泡摆位共用同一份。
    /// 用计算属性而非 static let：L() 依赖运行时语言设置，static let 只会算一次，
    /// 用户切换语言后文案不会跟着变。
    static var ringSpecs: [(scale: Double, label: String)] {
        [(0.34, L("1周内")), (0.68, L("2周内")), (1.0, L("1月内"))]
    }

    /// 场边距：最外环（scale 1.0）到容器四边留出的空白，给气泡的阴影 + 右上角「新」
    /// 角标 + 拖拽放大留余量。以前最外环半径直接取 min(w,h)/2，环线正好压在容器边上，
    /// 落在最外环、角度又指向边缘的气泡（尤其是那颗被推到远端的孤立卖点）就会被
    /// 圆角容器裁掉一半。现在把「场半径」整体内缩这个边距，环线和气泡一起内移。
    static let fieldInset: Double = 18

    /// 气泡场的有效半径：min(w,h)/2 再内缩 fieldInset。参考环、ringRadius、
    /// ringBandBounds、resolveOverlaps 全部以它为基准，保证环线与气泡摆位一致内缩。
    static func fieldRadius(width w: Double, height h: Double) -> Double {
        max(0, min(w, h) / 2 - fieldInset)
    }

    /// 每个环位内部按 daysAgo 线性插值的时间跨度上限（1月内档没有硬边界，用 30 天封顶）。
    private static let ringBandMaxDays: [Int] = [7, 14, 30]

    /// 时间距离 → 具体半径（不再是卡死在环线上的三个定值）：同一环位内部也按 daysAgo
    /// 线性插值，比如距查看日 3 天的信号落在「1周内」环（0~scale0）的 3/7 处，而不是
    /// 一律贴到 scale0 那条环线上——环线只是每个时间档的上限，不是气泡的固定摆放半径。
    static func ringRadius(forDaysAgo daysAgo: Int, fieldRadius: Double) -> Double {
        let scales = ringSpecs.map(\.scale)
        if daysAgo <= ringBandMaxDays[0] {
            let t = Double(daysAgo) / Double(ringBandMaxDays[0])
            return t * scales[0] * fieldRadius
        }
        if daysAgo <= ringBandMaxDays[1] {
            let t = Double(daysAgo - ringBandMaxDays[0]) / Double(ringBandMaxDays[1] - ringBandMaxDays[0])
            return (scales[0] + t * (scales[1] - scales[0])) * fieldRadius
        }
        let t = min(1.0, Double(daysAgo - ringBandMaxDays[1]) / Double(ringBandMaxDays[2] - ringBandMaxDays[1]))
        return (scales[1] + t * (scales[2] - scales[1])) * fieldRadius
    }

    /// 外圈本来就该塞得下更多气泡（越久远、越多信号还没被覆盖掉），所以额外按环位
    /// 把直径缩小一档，不然外圈越挤越点不到。和「买卖点级别」的大小是叠乘关系。
    static func ringSizeFactor(forDaysAgo daysAgo: Int) -> Double {
        if daysAgo <= 7 { return 1.0 }
        if daysAgo <= 14 { return 0.85 }
        return 0.7
    }

    /// 越远越淡：配合径向光晕，让"近实远虚"直接体现在气泡本身上，不用靠文字说明。
    static func ringOpacity(forDaysAgo daysAgo: Int) -> Double {
        if daysAgo <= 7 { return 1.0 }
        if daysAgo <= 14 { return 0.82 }
        return 0.6
    }

    private static func layoutBubbles(
        signals: [RadarSignal], dayDate: String, width w: Double, height h: Double
    ) -> [BubbleLayout] {
        guard !signals.isEmpty else { return [] }
        let golden = 2.399963
        // 与参考环共用的内缩场半径：最外环不贴容器边，气泡才不会被圆角容器裁掉。
        let fieldRadius = SignalRadarView.fieldRadius(width: w, height: h)

        var layouts: [BubbleLayout] = signals.enumerated().map { index, sig in
            let da = daysAgo(from: sig.date, to: dayDate)
            let diameter = SignalRadarView.diameter(forLevel: sig.level) * ringSizeFactor(forDaysAgo: da)
            let r = diameter / 2
            let maxRadius = fieldRadius - r - 4
            let radius = min(ringRadius(forDaysAgo: da, fieldRadius: fieldRadius), maxRadius)
            var x = w / 2 + radius * cos(Double(index) * golden)
            var y = h / 2 + radius * sin(Double(index) * golden)
            x = min(max(x, r + 2), w - r - 2)
            y = min(max(y, r + 2), h - r - 2)
            return BubbleLayout(signal: sig, diameter: diameter, x: x, y: y, phase: Double(index) * 0.35, daysAgo: da)
        }
        resolveOverlaps(&layouts, width: w, height: h, fieldRadius: fieldRadius)
        // 同一环内谁在最上层：越接近查看日（daysAgo 越小）画得越晚，叠层里就浮在
        // 更外面（更靠近用户）；离得越久远的沉在下面。
        layouts.sort { $0.daysAgo > $1.daysAgo }
        return layouts
    }

    /// 某个 daysAgo 所属环位允许的半径范围（相对场中心，单位与 fieldRadius 一致）。
    /// 直接用 ringSpecs 的三条环线本身做边界（而不是环线之间取中点）：「1周内」气泡的
    /// 圆心必须落在 0~scale0 这条环线画出的圆盘内部，不能越过环线本身混进「2周内」的
    /// 视觉区域；「2周内」「1月内」同理各自卡在自己两条环线之间。
    private static func ringBandBounds(forDaysAgo daysAgo: Int, fieldRadius: Double) -> (min: Double, max: Double) {
        let scales = ringSpecs.map(\.scale)
        if daysAgo <= ringBandMaxDays[0] { return (0, scales[0] * fieldRadius) }
        if daysAgo <= ringBandMaxDays[1] { return (scales[0] * fieldRadius, scales[1] * fieldRadius) }
        return (scales[1] * fieldRadius, scales[2] * fieldRadius)
    }

    /// 简单的迭代松弛：每一对挤太近的气泡沿连心线互相推开，直到间距 >= 两者半径和
    /// 的 90%（留一点点重叠的自然感，但不能像之前那样能整个盖住点不到）。
    private static func resolveOverlaps(
        _ layouts: inout [BubbleLayout], width w: Double, height h: Double, fieldRadius: Double
    ) {
        let minFactor = 0.9
        let cx = w / 2, cy = h / 2
        for _ in 0..<12 {
            for i in 0..<layouts.count {
                for j in (i + 1)..<layouts.count {
                    let dx = layouts[j].x - layouts[i].x
                    let dy = layouts[j].y - layouts[i].y
                    let dist = max((dx * dx + dy * dy).squareRoot(), 0.001)
                    let minDist = (layouts[i].diameter + layouts[j].diameter) / 2 * minFactor
                    guard dist < minDist else { continue }
                    let overlap = (minDist - dist) / 2
                    let ux = dx / dist, uy = dy / dist
                    layouts[i].x -= ux * overlap
                    layouts[i].y -= uy * overlap
                    layouts[j].x += ux * overlap
                    layouts[j].y += uy * overlap
                }
            }
            for i in 0..<layouts.count {
                let r = layouts[i].diameter / 2
                layouts[i].x = min(max(layouts[i].x, r + 2), w - r - 2)
                layouts[i].y = min(max(layouts[i].y, r + 2), h - r - 2)
                // 径向回拉：碰撞推挤只允许改变角度，不允许把气泡挤出自己所属的环位半径带
                // （否则一个刚出现的 daysAgo=0 信号会被外环的拥挤挤到外环去，居中程度失真）。
                let band = ringBandBounds(forDaysAgo: layouts[i].daysAgo, fieldRadius: fieldRadius)
                let dx = layouts[i].x - cx
                let dy = layouts[i].y - cy
                let dist = max((dx * dx + dy * dy).squareRoot(), 0.001)
                let maxAllowed = min(band.max, fieldRadius - r - 4)
                let clampedDist = min(max(dist, band.min), maxAllowed)
                if abs(clampedDist - dist) > 0.01 {
                    let scale = clampedDist / dist
                    layouts[i].x = cx + dx * scale
                    layouts[i].y = cy + dy * scale
                }
            }
        }
    }

    /// 买卖点级别 → 气泡直径：一类潜在空间最大（能捕捉到从底部开始的整段反转），
    /// 三类最小（只剩突破后的延续段）。
    /// 「确定性」不再叠加到大小上——之前把确定性也塞进大小，会跟深浅（形态技术面
    /// 强弱）读成同一件事，两个独立维度混成了一个。确定性改用气泡边框实/虚线表达
    /// （见 RadarBubble，跟图表页「虚线=未确认」同一套语言），大小专心只管潜在空间。
    static func diameter(forLevel level: Int) -> Double {
        switch level {
        case 1: return 92
        case 2: return 76
        default: return 60  // 三类
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

    /// 形态强度 → 气泡颜色：买（亮红→深红）/ 卖（亮绿→深绿）。
    static func bubbleColor(side: String, strength: Double) -> Color {
        let t = min(max(strength, 0), 1)
        func lerp(_ a: Double, _ b: Double) -> Double { a + (b - a) * t }
        if side == "buy" {
            return Color(.sRGB,
                         red: lerp(248, 120) / 255, green: lerp(113, 15) / 255, blue: lerp(133, 38) / 255)
        }
        return Color(.sRGB,
                     red: lerp(110, 4) / 255, green: lerp(231, 90) / 255, blue: lerp(183, 64) / 255)
    }

    // MARK: - 图例

    private var legend: some View {
        // 大小、深浅、边框分别管三件不同的事，拆成独立行说清楚，不然挤在一起
        // 用户会把"大小"和"深浅"都读成"这个信号有多强"，浪费一个维度。
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 14) {
                legendBar(label: L("买"), color: Theme.up,
                          gradient: [Color(hex: 0xF87185), Color(hex: 0x780F26)])
                legendBar(label: L("卖"), color: Theme.down,
                          gradient: [Color(hex: 0x6EE7B7), Color(hex: 0x045A40)])
            }
            HStack(spacing: 6) {
                Text(L("大小=潜在空间")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                levelDot(diameter: SignalRadarView.diameter(forLevel: 1), label: L("一类"))
                levelDot(diameter: SignalRadarView.diameter(forLevel: 2), label: L("二类"))
                levelDot(diameter: SignalRadarView.diameter(forLevel: 3), label: L("三类"))
            }
            Text(L("深浅=强弱 · 虚线边框=未确认 · 居中=越新 · 点击查看分析"))
                .font(.system(size: 10))
                .foregroundColor(Theme.textSecondary)
        }
    }

    /// 图例里的买卖点级别参考点：真实按 `diameter(forLevel:)` 等比缩小展示。
    private func levelDot(diameter: Double, label: String) -> some View {
        HStack(spacing: 3) {
            Circle().fill(Theme.textSecondary).frame(width: diameter * 0.16, height: diameter * 0.16)
            Text(label).font(.system(size: 9)).foregroundColor(Theme.textSecondary)
        }
    }

    private func legendBar(label: String, color: Color, gradient: [Color]) -> some View {
        HStack(spacing: 6) {
            Text(label).font(.caption.bold()).foregroundColor(color)
            RoundedRectangle(cornerRadius: 999)
                .fill(LinearGradient(colors: gradient, startPoint: .leading, endPoint: .trailing))
                .frame(height: 7)
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
                Text(index == 0 ? L("今日") : SignalRadarView.weekday(day.date))
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
        let scope = vm.response?.etfName ?? vm.market.title
        return VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text(L("正在扫描「%@」成分股…", scope))
                .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
            Text(L("首次扫描较慢，稍候即可看到每日买卖点"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
        VStack(spacing: 12) {
            Image(systemName: "dot.radiowaves.left.and.right")
                .font(.largeTitle).foregroundColor(Theme.textSecondary)
            Text(L("近期暂无买卖点信号"))
                .font(.subheadline).foregroundColor(Theme.textPrimary)
            Button(L("刷新")) { Task { await vm.refresh() } }
                .buttonStyle(.bordered).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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

    /// 星期几按当前界面语言本地化（中文「周一」/ 英文「Mon」），不再硬编码中文。
    static func weekday(_ date: String) -> String {
        guard let d = parser.date(from: date) else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: Localized.language().localeIdentifier)
        f.setLocalizedDateFormatFromTemplate("EEE")
        return f.string(from: d)
    }
}

/// 单个信号气泡：纯色实心 + 持续轻微漂浮 + 可按住拖拽（松手弹回原位）。
private struct RadarBubble: View {
    let signal: RadarSignal
    let diameter: CGFloat
    let baseX: CGFloat
    let baseY: CGFloat
    let phase: Double
    let color: Color
    /// 离查看日越远越淡（1.0=当日新增），配合中心光晕做出"近实远虚"的纵深感。
    let fade: Double
    /// 信号是不是查看这天当天新出现的（而非从更早的日子延续到现在）。
    let isNew: Bool
    let onOpen: () -> Void

    /// 持续漂浮的竖向偏移（onAppear 后在 0 ↔ 负值间无限往复）。
    @State private var floatY: CGFloat = 0
    /// 拖拽偏移；松手后用弹簧动画归零。
    @State private var drag: CGSize = .zero
    /// 拖拽中放大一点，给「被拎起来」的反馈。
    @State private var dragging = false

    private var r: CGFloat { diameter / 2 }

    var body: some View {
        content
            .frame(width: diameter, height: diameter)
            .opacity(fade)
            .scaleEffect(dragging ? 1.12 : 1.0)
            .offset(y: floatY)
            .offset(drag)
            .shadow(color: .black.opacity((dragging ? 0.5 : 0.35) * fade),
                    radius: dragging ? 12 : 6, y: dragging ? 8 : 3)
            .contentShape(Circle())
            .gesture(
                DragGesture()
                    .onChanged { value in
                        if !dragging { withAnimation(.easeOut(duration: 0.15)) { dragging = true } }
                        drag = value.translation
                    }
                    .onEnded { _ in
                        withAnimation(.spring(response: 0.45, dampingFraction: 0.55)) {
                            drag = .zero
                        }
                        withAnimation(.easeOut(duration: 0.2)) { dragging = false }
                    }
            )
            .onTapGesture { onOpen() }
            .position(x: baseX, y: baseY)
            .accessibilityElement()
            .accessibilityLabel(
                "\(signal.symbol) \(signal.name) \(signal.isBuy ? L("买点") : L("卖点"))"
                + (isNew ? " \(L("所选日期当天新增"))" : "")
            )
            .accessibilityAddTraits(.isButton)
            .onAppear {
                floatY = -6
                withAnimation(
                    .easeInOut(duration: Double.random(in: 2.2...3.4))
                        .repeatForever(autoreverses: true)
                        .delay(phase * 0.2)
                ) {
                    floatY = 6
                }
            }
    }

    private var content: some View {
        ZStack {
            // 纯实色气泡；未确认的信号额外描一圈虚线边框——跟图表页「虚线=未确认」
            // 同一套语言，确认的信号维持无描边的纯实色（多数信号都是已确认的，
            // 不想让所有气泡都套上边框，那样反而弱化了「未确认」这个特殊标记）。
            Circle().fill(color)
            if !signal.confirmed {
                Circle().stroke(style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
                    .foregroundColor(.white.opacity(0.85))
            }

            VStack(spacing: 1) {
                Text(signal.symbol)
                    .font(.system(size: max(12, min(17, r * 0.42)), weight: .heavy))
                    .foregroundColor(.white)
                Text(signal.name)
                    .font(.system(size: max(9, min(12, r * 0.3))))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .padding(.horizontal, 4)
            }
            .shadow(color: .black.opacity(0.4), radius: 2, y: 1)
        }
        .overlay(alignment: .topTrailing) {
            // "新"改放气泡外面右上角：挤在气泡内部会跟代码/名称文字抢地方。
            if isNew {
                Text(L("新"))
                    .font(.system(size: max(8, r * 0.22), weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Theme.segment)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(Theme.background, lineWidth: 1))
                    .offset(x: 4, y: -4)
            }
        }
    }
}
