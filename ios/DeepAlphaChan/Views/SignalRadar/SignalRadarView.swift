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
                    Spacer(minLength: 0)
                    dateRail
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
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
                        bubble(sig, index: idx, width: w, height: h)
                    }
                    Text(L("越靠中心 · 形态技术面越强"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .position(x: CGFloat(w / 2), y: 12)
                }
            }
        }
        .frame(height: 360)
        .background(Theme.surface.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
    }

    /// 单个气泡：向日葵螺旋摆位（最强居中），大小/颜色随形态强度。
    private func bubble(_ sig: RadarSignal, index: Int, width w: Double, height h: Double) -> some View {
        let diameter = 48.0 + sig.strength * 40.0
        let r = diameter / 2
        let golden = 2.399963
        let spacing = min(w, h) * 0.11
        let radius = spacing * Double(index).squareRoot()
        var x = w / 2 + radius * cos(Double(index) * golden)
        var y = h / 2 + radius * sin(Double(index) * golden)
        x = min(max(x, r + 2), w - r - 2)
        y = min(max(y, r + 2), h - r - 2)
        let isTop = index == 0

        return Button {
            onOpenSymbol(vm.market.rawValue, sig.symbol)
        } label: {
            VStack(spacing: 1) {
                Text(sig.symbol)
                    .font(.system(size: CGFloat(max(12, min(17, r * 0.42))), weight: .heavy))
                    .foregroundColor(.white)
                Text(sig.name)
                    .font(.system(size: CGFloat(max(9, min(12, r * 0.3)))))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .padding(.horizontal, 4)
            }
            .frame(width: CGFloat(diameter), height: CGFloat(diameter))
            .background(SignalRadarView.bubbleColor(side: sig.side, strength: sig.strength))
            .clipShape(Circle())
            .overlay(
                Circle().stroke(Color.white.opacity(isTop ? 0.85 : 0), lineWidth: 2)
            )
            .shadow(color: .black.opacity(0.4), radius: 6, y: 3)
        }
        .buttonStyle(.plain)
        .position(x: CGFloat(x), y: CGFloat(y))
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
