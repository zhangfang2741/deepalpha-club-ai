import SwiftUI

/// 信号雷达 Tab —— 扫描各市场科技 ETF 成分股跑缠论，把每日买卖点前 10 只用气泡呈现。
///
/// 气泡编码：颜色区分方向（红=买点 / 绿=卖点），颜色深浅与大小统一由「形态技术面强度」
/// 驱动（越强越深越大，最强居中）。底部可横滑的日期轨手动选某一天，看当天信号。
/// 点气泡跳到缠论分析详情页（复用晨报「重点个股」的 onOpenSymbol 跳转机制）。
struct SignalRadarView: View {
    /// 个股跳转回调：(market, symbol) → 切到分析 Tab 跑缠论。
    let onOpenSymbol: (String, String) -> Void

    @StateObject private var vm = SignalRadarViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                marketSwitch

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
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 10)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Theme.background)
            .navigationTitle(L("信号雷达"))
            .navigationBarTitleDisplayMode(.inline)
            .task { vm.onAppear() }
        }
    }

    // MARK: - 市场切换

    private var marketSwitch: some View {
        Picker("", selection: Binding(
            get: { vm.market },
            set: { vm.switchMarket($0) }
        )) {
            ForEach(StockMarket.allCases) { m in
                Text(m.title).tag(m)
            }
        }
        .pickerStyle(.segmented)
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
            let signals = (vm.selectedDay?.signals ?? [])
                .sorted { $0.strength > $1.strength }
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
                        bubble(sig, index: idx, count: signals.count, width: w, height: h)
                    }
                    Text(L("越靠中心 · 形态技术面越强"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: 12)
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
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
    }

    /// 单个气泡：向日葵螺旋摆位（最强居中），大小/颜色随形态强度。
    private func bubble(_ sig: RadarSignal, index: Int, count: Int, width w: Double, height h: Double) -> some View {
        let diameter = 48.0 + sig.strength * 40.0
        let r = diameter / 2
        // 向日葵螺旋 + 归一化到整个气泡场的椭圆铺满：最强(index 0)居中，其余向四周
        // 均匀铺开，随气泡场宽高自适应，避免高屏上挤成中间一小团。
        let golden = 2.399963
        let maxIdx = Double(max(count - 1, 1))
        let frac = (Double(index) / maxIdx).squareRoot()
        let ang = Double(index) * golden
        let rx = max(0, w / 2 - r - 8) * frac
        let ry = max(0, h / 2 - r - 8) * frac
        let x = w / 2 + rx * cos(ang)
        let y = h / 2 + ry * sin(ang)

        return RadarBubble(
            signal: sig,
            diameter: CGFloat(diameter),
            baseX: CGFloat(x),
            baseY: CGFloat(y),
            isTop: index == 0,
            phase: Double(index) * 0.35,
            color: SignalRadarView.bubbleColor(side: sig.side, strength: sig.strength),
            onOpen: { onOpenSymbol(vm.market.rawValue, sig.symbol) }
        )
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
            HStack(spacing: 6) {
                Circle().fill(Theme.textSecondary).frame(width: 7, height: 7)
                Circle().fill(Theme.textSecondary).frame(width: 13, height: 13)
                Text(L("越深 · 越大 = 形态技术面越强 · 点击查看分析"))
                    .font(.system(size: 10))
                    .foregroundColor(Theme.textSecondary)
            }
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

/// 单个信号气泡：半透明玻璃质感 + 持续轻微漂浮 + 可按住拖拽（松手弹回原位）。
private struct RadarBubble: View {
    let signal: RadarSignal
    let diameter: CGFloat
    let baseX: CGFloat
    let baseY: CGFloat
    let isTop: Bool
    let phase: Double
    let color: Color
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
            .accessibilityLabel("\(signal.symbol) \(signal.name) \(signal.isBuy ? L("买点") : L("卖点"))")
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
            // 纯实色气泡，无透明、无描边
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
            .shadow(color: .black.opacity(0.4), radius: 2, y: 1)
        }
    }
}
