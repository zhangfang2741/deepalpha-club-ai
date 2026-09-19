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
            let maxDaysAgo = Double(
                signals.map { SignalRadarView.daysAgo(from: $0.date, to: dayDate) }.max() ?? 0
            )
            ZStack {
                // 同心参考环
                ForEach([0.34, 0.68, 1.0], id: \.self) { scale in
                    Circle()
                        .stroke(Theme.textSecondary.opacity(0.10),
                                style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        .frame(width: CGFloat(base * scale), height: CGFloat(base * scale))
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                }

                if signals.isEmpty {
                    Text(L("当日无买卖点信号"))
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: CGFloat(h / 2))
                } else {
                    ForEach(Array(signals.enumerated()), id: \.element.id) { idx, sig in
                        bubble(sig, index: idx, dayDate: dayDate, maxDaysAgo: maxDaysAgo, width: w, height: h)
                    }
                    Text(L("越靠中心 · 信号越新（NEW=当日新增）"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: 12)
                }
            }
        }
        .frame(height: 360)
        .background(Theme.surface.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    /// 单个气泡：角度按向日葵螺旋摆开（避免同距离的挤成一条线），到中心的距离由
    /// 「离查看日多少天」决定，大小由买卖点级别决定，颜色由方向+强度决定。
    private func bubble(
        _ sig: RadarSignal, index: Int, dayDate: String, maxDaysAgo: Double, width w: Double, height h: Double
    ) -> some View {
        let diameter = SignalRadarView.diameter(forLevel: sig.level)
        let r = diameter / 2
        let golden = 2.399963
        let maxRadius = min(w, h) / 2 - r - 4
        let daysAgo = Double(SignalRadarView.daysAgo(from: sig.date, to: dayDate))
        let t = maxDaysAgo > 0 ? min(daysAgo / maxDaysAgo, 1.0) : 0
        let radius = t * maxRadius
        var x = w / 2 + radius * cos(Double(index) * golden)
        var y = h / 2 + radius * sin(Double(index) * golden)
        x = min(max(x, r + 2), w - r - 2)
        y = min(max(y, r + 2), h - r - 2)

        return RadarBubble(
            signal: sig,
            diameter: CGFloat(diameter),
            baseX: CGFloat(x),
            baseY: CGFloat(y),
            phase: Double(index) * 0.35,
            color: SignalRadarView.bubbleColor(side: sig.side, strength: sig.strength),
            isNew: sig.date == dayDate,
            onOpen: { openSymbol(sig.symbol) }
        )
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
        guard let s = parser.date(from: signalDate), let v = parser.date(from: viewedDate) else { return 0 }
        let days = Calendar(identifier: .gregorian).dateComponents([.day], from: s, to: v).day ?? 0
        return max(0, days)
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
                }
                .padding(.horizontal, 2)
            }
        }
    }

    private func dayChip(_ day: RadarDay, index: Int) -> some View {
        let active = index == min(max(vm.selectedDayIndex, 0), vm.days.count - 1)
        let buyFrac = day.total > 0 ? CGFloat(day.buyCount) / CGFloat(day.total) : 0.5
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
            .scaleEffect(dragging ? 1.12 : 1.0)
            .offset(y: floatY)
            .offset(drag)
            .shadow(color: .black.opacity(dragging ? 0.5 : 0.35),
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
                Text(signal.symbol)
                    .font(.system(size: max(12, min(17, r * 0.42)), weight: .heavy))
                    .foregroundColor(.white)
                Text(signal.name)
                    .font(.system(size: max(9, min(12, r * 0.3))))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .padding(.horizontal, 4)
            }
            .shadow(color: .black.opacity(0.5), radius: 2, y: 1)
        }
        .overlay(alignment: .topTrailing) {
            if isNew {
                Text(L("新"))
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1.5)
                    .background(Theme.accent)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(Color.white.opacity(0.7), lineWidth: 0.5))
                    .offset(x: 4, y: -4)
            }
        }
    }
}
