import SwiftUI

/// 主图上可以点按开关的叠加指标（图表下方的指标栏，见 `IndicatorBar`）。
/// 成交量与 MACD 副图固定显示、不在这里（缠论的背驰要对照 MACD 面积，不让关）。
///
/// **新增指标**按这几步，别的地方不用动：
/// 1. 这里加一个 case，写 `title`、`defaultOn`；
/// 2. 数据：后端 `/chan/analysis` 加对应字段（按合并 K 线对齐，见 `app/services/chan/indicators.py`），`ChanAnalysis` 加属性，
///    并在 `IndicatorBar.isAvailable` 里写「什么时候有数据」（没有数据的指标不显示开关）；
/// 3. 画：`ChanChartView.priceChart` 的 Canvas 里加（用 `vm.isOn(.xxx)` 判断），左上角数值行 `indicatorValues` 加一段；
/// 4. 参数可调的话在 `IndicatorSettings` / `IndicatorSettingsSheet` 加一项，后端 `/chan/analysis` 加对应查询参数；
/// 5. 名词要补 `glossary.json`（中英）。
enum ChartIndicator: String, CaseIterable, Identifiable {
    case ma, ema, boll

    var id: String { rawValue }

    var title: String {
        switch self {
        case .ma: return L("均线")
        case .ema: return "EMA"
        case .boll: return "BOLL"
        }
    }

    /// 用户没动过它时是开还是关。新增指标默认关最稳，不会让老用户的图面突然变样。
    var defaultOn: Bool { self == .ma }
}

/// 用户的开关选择存本机。存「用户明确选过的」{指标 id: 开 / 关}，没选过的走 `defaultOn`：
/// 以后新增指标、或改某个指标的默认值，都不会被老用户存下的旧状态盖掉。
enum ChartIndicatorStore {
    private static let key = "chart.indicators.v1"

    static func load() -> [String: Bool] {
        UserDefaults.standard.dictionary(forKey: key) as? [String: Bool] ?? [:]
    }

    static func save(_ choices: [String: Bool]) {
        UserDefaults.standard.set(choices, forKey: key)
    }
}

/// 用户自定义的指标参数（「指标设置」面板）。nil = 用后端默认（均线按周期：日线 / 30 分钟 5·20·60，周线 5·10·20）。
/// 范围与后端 `app/services/chan/indicators.py` 一致：周期 2~250，均线最多 3 条、EMA 最多 2 条（= 各自的颜色数），
/// BOLL 倍数 0.5~5；越界的后端会回退默认，所以这里也按同一范围限制输入。
struct IndicatorSettings: Codable, Equatable {
    var ma: [Int]? = nil
    var ema: [Int]? = nil
    var bollPeriod: Int? = nil
    var bollMult: Double? = nil

    static let periodRange = 2...250
    static let multRange = 0.5...5.0
    static let defaultEMA = [12, 26]
    static let defaultBoll = (period: 20, mult: 2.0)

    private static let key = "chart.indicatorParams.v1"

    static func load() -> IndicatorSettings {
        guard let data = UserDefaults.standard.data(forKey: key),
              let s = try? JSONDecoder().decode(IndicatorSettings.self, from: data) else { return IndicatorSettings() }
        return s
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) { UserDefaults.standard.set(data, forKey: Self.key) }
    }

    /// `/chan/analysis` 的查询参数；没改过的不传（后端用默认，旧逻辑不变）。
    var queryItems: [String: String] {
        var q: [String: String] = [:]
        if let ma, !ma.isEmpty { q["ma"] = ma.map(String.init).joined(separator: ",") }
        if let ema, !ema.isEmpty { q["ema"] = ema.map(String.init).joined(separator: ",") }
        if let bollPeriod, let bollMult { q["boll"] = "\(bollPeriod),\(bollMult)" }
        return q
    }
}

/// 图表下方的指标栏（参考富途）：一行纯文字，选中的变色加粗，点一下开 / 关；最右边是参数设置。
/// 各条线的数值不在这里，在主图左上角（随十字光标变化，见 `ChanChartView.indicatorValues`）。
struct IndicatorBar: View {
    @ObservedObject var vm: ChanViewModel
    let analysis: ChanAnalysis
    @State private var showSettings = false

    /// 这张图有没有这个指标的数据；没有就不放开关（比如旧后端没有均线）。
    private func isAvailable(_ i: ChartIndicator) -> Bool {
        switch i {
        case .ma: return !(analysis.ma?.periods.isEmpty ?? true)
        case .ema: return !(analysis.ema?.periods.isEmpty ?? true)
        case .boll: return analysis.boll != nil
        }
    }

    var body: some View {
        let items = ChartIndicator.allCases.filter(isAvailable)
        if !items.isEmpty {
            HStack(spacing: 0) {
                ForEach(items) { tab($0) }
                Spacer(minLength: 0)
                Button {
                    showSettings = true
                } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Theme.textSecondary)
                        .frame(width: 44, height: 36)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(L("指标设置"))
            }
            .sheet(isPresented: $showSettings) {
                IndicatorSettingsSheet(vm: vm, analysis: analysis)
                    .preferredColorScheme(.dark)
                    .presentationDetents([.medium, .large])
            }
        }
    }

    private func tab(_ i: ChartIndicator) -> some View {
        let on = vm.isOn(i)
        return Button {
            vm.toggle(i)
        } label: {
            Text(i.title)
                .font(.system(size: 12, weight: on ? .semibold : .regular))
                .foregroundStyle(on ? Theme.accent : Theme.textSecondary)
                .padding(.horizontal, 12)
                .frame(minHeight: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(i.title)
        .accessibilityAddTraits(on ? AccessibilityTraits([.isButton, .isSelected]) : AccessibilityTraits.isButton)
    }
}

/// 指标参数设置：均线 3 条 / EMA 2 条的周期（每条可单独关掉）、BOLL 的周期与倍数。
/// 点「完成」才生效（改了才重新请求一次分析）；「恢复默认」清掉自定义。
struct IndicatorSettingsSheet: View {
    @ObservedObject var vm: ChanViewModel
    let analysis: ChanAnalysis
    @Environment(\.dismiss) private var dismiss

    /// 每条线：周期 + 是否启用。
    struct Line: Identifiable { let id: Int; var period: Int; var enabled: Bool }

    @State private var maLines: [Line] = []
    @State private var emaLines: [Line] = []
    @State private var bollPeriod = IndicatorSettings.defaultBoll.period
    @State private var bollMult = IndicatorSettings.defaultBoll.mult

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ForEach($maLines) { lineRow($0, prefix: "MA", colors: Theme.maColors) }
                } header: {
                    Text(L("均线"))
                } footer: {
                    Text(L("最近 N 根 K 线收盘价的平均。"))
                }
                Section {
                    ForEach($emaLines) { lineRow($0, prefix: "EMA", colors: Theme.emaColors) }
                } header: {
                    Text("EMA")
                } footer: {
                    Text(L("指数移动平均：越近的 K 线权重越大，比均线拐得快。"))
                }
                Section {
                    Stepper(value: $bollPeriod, in: IndicatorSettings.periodRange) {
                        valueLabel(L("周期"), "\(bollPeriod)", color: Theme.bollLine)
                    }
                    Stepper(value: $bollMult, in: IndicatorSettings.multRange, step: 0.5) {
                        valueLabel(L("标准差倍数"), String(format: "%.1f", bollMult), color: Theme.bollLine)
                    }
                } header: {
                    Text("BOLL")
                } footer: {
                    Text(L("中轨是 N 根 K 线的均线，上下轨 = 中轨 ± 倍数 × 标准差。"))
                }
                Section {
                    Button(L("恢复默认")) { fill(from: IndicatorSettings()) }
                }
            }
            .navigationTitle(L("指标设置"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("取消")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("完成")) { apply() }
                }
            }
        }
        .onAppear { fill(from: vm.indicatorSettings) }
    }

    private func lineRow(_ line: Binding<Line>, prefix: String, colors: [Color]) -> some View {
        let color = colors[min(line.wrappedValue.id, colors.count - 1)]
        return HStack {
            Toggle("", isOn: line.enabled).labelsHidden()
            Stepper(value: line.period, in: IndicatorSettings.periodRange) {
                valueLabel("\(prefix)\(line.wrappedValue.id + 1)", "\(line.wrappedValue.period)", color: color)
            }
            .disabled(!line.wrappedValue.enabled)
            .opacity(line.wrappedValue.enabled ? 1 : 0.45)
        }
    }

    private func valueLabel(_ name: String, _ value: String, color: Color) -> some View {
        HStack(spacing: 8) {
            Capsule().fill(color).frame(width: 12, height: 3)
            Text(name).foregroundStyle(Theme.textSecondary)
            Text(value).font(.body.monospacedDigit()).foregroundStyle(Theme.textPrimary)
        }
    }

    /// 用设置填表；没自定义过的用默认（均线默认随周期，与后端 `ma.MA_PERIODS` 一致）。
    private func fill(from s: IndicatorSettings) {
        let maDefault = ChanViewModel.defaultMAPeriods(freq: vm.freq)
        maLines = Self.lines(s.ma ?? maDefault, slots: Theme.maColors.count, fallback: maDefault)
        emaLines = Self.lines(s.ema ?? IndicatorSettings.defaultEMA, slots: Theme.emaColors.count,
                              fallback: IndicatorSettings.defaultEMA)
        bollPeriod = s.bollPeriod ?? IndicatorSettings.defaultBoll.period
        bollMult = s.bollMult ?? IndicatorSettings.defaultBoll.mult
    }

    /// 固定槽位（= 颜色数）：已有的周期启用，空槽用默认周期但关着。
    private static func lines(_ periods: [Int], slots: Int, fallback: [Int]) -> [Line] {
        (0..<slots).map { k in
            k < periods.count
                ? Line(id: k, period: periods[k], enabled: true)
                : Line(id: k, period: fallback[min(k, fallback.count - 1)], enabled: false)
        }
    }

    private func apply() {
        let ma = maLines.filter(\.enabled).map(\.period)
        let ema = emaLines.filter(\.enabled).map(\.period)
        var s = IndicatorSettings()
        // 与默认相同的就不存，保持「没改过」（均线默认随周期变，存下来就不随了）
        let maDefault = ChanViewModel.defaultMAPeriods(freq: vm.freq)
        s.ma = ma.isEmpty || Set(ma) == Set(maDefault) ? nil : Array(Set(ma)).sorted()
        s.ema = ema.isEmpty || Set(ema) == Set(IndicatorSettings.defaultEMA) ? nil : Array(Set(ema)).sorted()
        if bollPeriod != IndicatorSettings.defaultBoll.period || bollMult != IndicatorSettings.defaultBoll.mult {
            s.bollPeriod = bollPeriod
            s.bollMult = bollMult
        }
        vm.updateIndicatorSettings(s)
        dismiss()
    }
}
