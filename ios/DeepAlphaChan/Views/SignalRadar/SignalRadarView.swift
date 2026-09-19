import SwiftUI

/// 信号雷达 Tab —— 扫描各市场科技 ETF 成分股跑缠论，把每日买卖点前 10 只用气泡呈现。
///
/// 顶部市场选择与三地恐慌指数小卡片合二为一（PanicIndexStrip）：点哪张卡就切到
/// 哪个市场，不再单独放一条分段选择器。
///
/// 气泡编码（三个视觉维度对应三件不同的事，不再互相重复）：
/// - 颜色：方向（红=买点 / 绿=卖点）+ 深浅（形态技术面强弱）；
/// - 大小：买卖点级别（一类最大 → 三类最小），级别是缠论里结构意义的分类；
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
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Theme.background)
            .navigationTitle(L("信号雷达"))
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
                    Circle()
                        .stroke(Theme.textSecondary.opacity(0.16 - Double(idx) * 0.045),
                                style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        .frame(width: CGFloat(base * spec.scale), height: CGFloat(base * spec.scale))
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                    Text(spec.label)
                        .font(.system(size: 8))
                        .foregroundColor(Theme.textSecondary.opacity(0.55))
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2) - CGFloat(base * spec.scale / 2) + 8)
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
        .frame(height: 360)
        .background(Theme.surface.opacity(0.4))
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

    /// 时间距离 → 三档环位（对应 ringSpecs 的 0.34 / 0.68 / 1.0 三个半径比例）。
    static func ringScale(forDaysAgo daysAgo: Int) -> Double {
        if daysAgo <= 7 { return ringSpecs[0].scale }
        if daysAgo <= 14 { return ringSpecs[1].scale }
        return ringSpecs[2].scale
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
        let fieldRadius = min(w, h) / 2

        var layouts: [BubbleLayout] = signals.enumerated().map { index, sig in
            let da = daysAgo(from: sig.date, to: dayDate)
            let diameter = SignalRadarView.diameter(forLevel: sig.level) * ringSizeFactor(forDaysAgo: da)
            let r = diameter / 2
            let maxRadius = fieldRadius - r - 4
            let radius = min(ringScale(forDaysAgo: da) * fieldRadius, maxRadius)
            var x = w / 2 + radius * cos(Double(index) * golden)
            var y = h / 2 + radius * sin(Double(index) * golden)
            x = min(max(x, r + 2), w - r - 2)
            y = min(max(y, r + 2), h - r - 2)
            return BubbleLayout(signal: sig, diameter: diameter, x: x, y: y, phase: Double(index) * 0.35, daysAgo: da)
        }
        resolveOverlaps(&layouts, width: w, height: h)
        // 同一环内谁在最上层：越接近查看日（daysAgo 越小）画得越晚，叠层里就浮在
        // 更外面（更靠近用户）；离得越久远的沉在下面。
        layouts.sort { $0.daysAgo > $1.daysAgo }
        return layouts
    }

    /// 简单的迭代松弛：每一对挤太近的气泡沿连心线互相推开，直到间距 >= 两者半径和
    /// 的 90%（留一点点重叠的自然感，但不能像之前那样能整个盖住点不到）。
    private static func resolveOverlaps(_ layouts: inout [BubbleLayout], width w: Double, height h: Double) {
        let minFactor = 0.9
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
            }
        }
    }

    /// 买卖点级别 → 气泡直径：一类结构意义最强，气泡最大。
    static func diameter(forLevel level: Int) -> Double {
        switch level {
        case 1: return 84
        case 2: return 66
        default: return 50
        }
    }

    /// 信号诞生日 → 查看日的天数差（signal.date 恒 <= dayDate，见后端按日重建）。
    static func daysAgo(from signalDate: String, to viewedDate: String) -> Int {
        max(0, absDayDiff(signalDate, viewedDate))
    }

    /// 两个 yyyy-MM-dd 日期字符串相差多少天（可正可负；解析失败按 0 处理）。
    static func absDayDiff(_ a: String, _ b: String) -> Int {
        guard let da = parser.date(from: a), let db = parser.date(from: b) else { return 0 }
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
        VStack(spacing: 5) {
            HStack(spacing: 14) {
                legendBar(label: L("买"), color: Theme.up,
                          gradient: [Color(hex: 0xF87185), Color(hex: 0x780F26)])
                legendBar(label: L("卖"), color: Theme.down,
                          gradient: [Color(hex: 0x6EE7B7), Color(hex: 0x045A40)])
            }
            HStack(spacing: 5) {
                levelDot(diameter: SignalRadarView.diameter(forLevel: 1), label: L("一类"))
                levelDot(diameter: SignalRadarView.diameter(forLevel: 2), label: L("二类"))
                levelDot(diameter: SignalRadarView.diameter(forLevel: 3), label: L("三类"))
                Text(L("· 深浅=强弱 · 居中=越新 · 点击查看分析"))
                    .font(.system(size: 9))
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
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
                    ForEach(Array(vm.days.enumerated()), id: \.element.id) { idx, day in
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
        let buyFrac = day.total > 0 ? CGFloat(day.buyCount) / CGFloat(day.total) : 0.5
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
                GeometryReader { g in
                    HStack(spacing: 0) {
                        Rectangle().fill(Theme.up).frame(width: g.size.width * buyFrac)
                        Rectangle().fill(Theme.down)
                    }
                }
                .frame(width: 38, height: 4)
                .clipShape(Capsule())
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
        VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text(L("正在扫描全市场成分股…"))
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
    private static let weekdaySymbols = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]

    static func monthDay(_ date: String) -> String {
        let parts = date.split(separator: "-")
        return parts.count >= 3 ? "\(parts[1])-\(parts[2])" : date
    }

    static func weekday(_ date: String) -> String {
        guard let d = parser.date(from: date) else { return "" }
        let w = Calendar(identifier: .gregorian).component(.weekday, from: d)
        return weekdaySymbols[(w - 1 + 7) % 7]
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
                "\(signal.symbol) \(signal.name) \(signal.isBuy ? "买点" : "卖点")"
                + (isNew ? " \(L("当日新增"))" : "")
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
            // 纯色主体，不透明、不描边
            Circle().fill(color)

            VStack(spacing: 1) {
                HStack(spacing: 3) {
                    Text(signal.symbol)
                        .font(.system(size: max(12, min(17, r * 0.42)), weight: .heavy))
                        .foregroundColor(.white)
                    // "新"放气泡内部：放在外面角标容易被相邻重叠的气泡盖住看不见。
                    if isNew {
                        Text(L("新"))
                            .font(.system(size: max(7, r * 0.2), weight: .bold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 3.5)
                            .padding(.vertical, 1)
                            .background(Color.white.opacity(0.28))
                            .clipShape(Capsule())
                    }
                }
                Text(signal.name)
                    .font(.system(size: max(9, min(12, r * 0.3))))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .padding(.horizontal, 4)
            }
            .shadow(color: .black.opacity(0.5), radius: 2, y: 1)
        }
    }
}
