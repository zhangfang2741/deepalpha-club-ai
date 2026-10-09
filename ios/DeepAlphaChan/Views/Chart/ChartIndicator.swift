import SwiftUI

/// 图表上可以点按开关的指标（图表下方的指标栏，见 `IndicatorBar`）。
///
/// **新增指标**（以后加 BOLL / EMA / RSI 等）按这几步，别的地方不用动：
/// 1. 这里加一个 case，写 `slot`（叠在主图上 / 单独一个副图或底部区域）、`title`、`defaultOn`；
/// 2. 数据：后端 `/chan/analysis` 加对应字段（按合并 K 线对齐，见 `app/services/chan/ma.py`），`ChanAnalysis` 加属性，
///    并在 `IndicatorBar.isAvailable` 里写「什么时候有数据」（没有数据的指标不显示开关）；
/// 3. 画：`ChanChartView` 主图叠加类加进 `priceChart` 的 Canvas（用 `vm.isOn(.xxx)` 判断），副图类仿 `macdChart`；
/// 4. 名词要补 `glossary.json`（中英）。
enum ChartIndicator: String, CaseIterable, Identifiable {
    case ma, ema, boll, volume, macd

    /// 指标栏里分两组：叠在主图上的 / 底部的成交量与副图。
    enum Slot { case overlay, panel }

    var id: String { rawValue }

    var slot: Slot {
        switch self {
        case .ma, .ema, .boll: return .overlay
        case .volume, .macd: return .panel
        }
    }

    var title: String {
        switch self {
        case .ma: return L("均线")
        case .ema: return "EMA"
        case .boll: return "BOLL"
        case .volume: return L("成交量")
        case .macd: return "MACD"
        }
    }

    /// 用户没动过它时是开还是关。新增指标默认关最稳，不会让老用户的图面突然变样。
    var defaultOn: Bool {
        switch self {
        case .ma, .volume, .macd: return true
        case .ema, .boll: return false
        }
    }

    static var overlays: [ChartIndicator] { allCases.filter { $0.slot == .overlay } }
    static var panels: [ChartIndicator] { allCases.filter { $0.slot == .panel } }
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

/// 图表下方的指标栏：点一下开 / 关。高亮 = 已显示。横向可滚动，指标多了也放得下。
struct IndicatorBar: View {
    @ObservedObject var vm: ChanViewModel
    let analysis: ChanAnalysis

    /// 这张图有没有这个指标的数据；没有就不放开关（比如旧后端没有均线、指数没有成交量）。
    private func isAvailable(_ i: ChartIndicator) -> Bool {
        switch i {
        case .ma: return !(analysis.ma?.periods.isEmpty ?? true)
        case .ema: return !(analysis.ema?.periods.isEmpty ?? true)
        case .boll: return analysis.boll != nil
        case .volume: return analysis.mergedCandles.contains { ($0.volume ?? 0) > 0 }
        case .macd: return analysis.macd != nil
        }
    }

    var body: some View {
        let overlays = ChartIndicator.overlays.filter(isAvailable)
        let panels = ChartIndicator.panels.filter(isAvailable)
        if !overlays.isEmpty || !panels.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(overlays) { chip($0) }
                    if !overlays.isEmpty && !panels.isEmpty {
                        Rectangle().fill(Theme.border).frame(width: 1, height: 16).padding(.horizontal, 2)
                    }
                    ForEach(panels) { chip($0) }
                }
                .padding(.horizontal, 2)
            }
        }
    }

    /// 按周期画的指标（均线 / EMA）：周期列表和各条线的颜色。其他指标没有。
    private func lineKey(_ i: ChartIndicator) -> ([Int], [Color])? {
        switch i {
        case .ma: return analysis.ma.map { ($0.periods, Theme.maColors) }
        case .ema: return analysis.ema.map { ($0.periods, Theme.emaColors) }
        default: return nil
        }
    }

    private func chip(_ i: ChartIndicator) -> some View {
        let on = vm.isOn(i)
        return Button {
            vm.toggle(i)
        } label: {
            HStack(spacing: 4) {
                Text(i.title)
                // 均线 / EMA 打开时把各条线的颜色和周期写在旁边（5 20 60），看得懂哪条是哪条
                if on, let (periods, colors) = lineKey(i) {
                    ForEach(Array(periods.enumerated()), id: \.offset) { k, p in
                        Text("\(p)")
                            .font(.system(size: 9, weight: .semibold).monospacedDigit())
                            .foregroundStyle(colors[min(k, colors.count - 1)])
                    }
                }
            }
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(on ? Theme.accent : Theme.textSecondary)
            .padding(.horizontal, 10)
            .frame(minHeight: 44)  // 点击热区 ≥ 44pt
            .background(
                Capsule().fill(on ? Theme.accent.opacity(0.14) : Color.clear)
                    .padding(.vertical, 6)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(i.title)
        .accessibilityAddTraits(on ? AccessibilityTraits([.isButton, .isSelected]) : AccessibilityTraits.isButton)
    }
}
