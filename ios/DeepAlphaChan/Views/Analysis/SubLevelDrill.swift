import SwiftUI

/// 次级别下钻入口：紧贴日线图上方的一行结论（「30分 共振买 · 日线偏多 ›」）。
///
/// 交互取缠论「区间套」的思路——日线定方向、30 分钟找进出点：结论贴着图表放，
/// 看图时一眼可见；点一下从底部弹出 30 分钟图（半屏，可上拉全屏），日线页原样不动、
/// 不重新加载。想完整看 30 分钟分析，仍可用页面顶部的周期切换。
/// 只在日线分析显示；加载失败或后端未部署该接口时整行不出现，不打扰主结果。
struct SubLevelBar: View {
    @ObservedObject var vm: ChanViewModel
    /// 离屏渲染分享长图时置 true：保留结论，去掉点击。
    var isStatic = false

    @State private var showSheet = false

    var body: some View {
        if vm.freq == "daily" {
            if let sub = vm.subLevel {
                Button { showSheet = true } label: { row(sub) }
                    .buttonStyle(.plain)
                    .allowsHitTesting(!isStatic)
                    .accessibilityHint(L("打开 30 分钟图表"))
                    .sheet(isPresented: $showSheet) {
                        SubLevelSheet(parent: vm, sub: sub)
                    }
            } else if vm.subLevelLoading && !isStatic {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.mini)
                    Text(L("正在加载 30 分钟级别…"))
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 12)
                .frame(height: 36)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
            }
        }
    }

    static func shortBias(_ bias: String) -> String {
        switch bias {
        case "bullish": return L("日线偏多")
        case "bearish": return L("日线偏空")
        default: return L("日线中性")
        }
    }

        private func row(_ sub: SubLevel) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "scope")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.accent)
            Text(L("30分"))
                .font(.caption.weight(.semibold))
                .foregroundColor(Theme.textSecondary)
            VerdictBadge(sub: sub)
            // 一行放不下后端的完整方向描述，这里只给短标签；完整描述在浮层里
            Text(Self.shortBias(sub.dailyBias))
                .font(.caption)
                .foregroundColor(SignalFormatting.biasColor(sub.dailyBias))
                .lineLimit(1)
            if let last = sub.recentSignals.last {
                Text("· " + last.label)
                    .font(.caption)
                    .foregroundColor(last.isBuy ? Theme.up : Theme.down)
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            if !isStatic {
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .padding(.horizontal, 12)
        .frame(minHeight: 36)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
        .contentShape(Rectangle())
    }
}

/// 结论徽标：共振买=涨色、共振卖=跌色、逆势=橙色警示、等待/不可用=灰。
struct VerdictBadge: View {
    let sub: SubLevel

    var body: some View {
        Text(sub.verdictLabel)
            .font(.caption.weight(.semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(Self.color(sub.verdict)))
    }

    static func color(_ verdict: SubLevel.Verdict) -> Color {
        switch verdict {
        case .resonanceBuy: return Theme.up
        case .resonanceSell: return Theme.down
        case .counterTrend: return Theme.segment
        case .waiting, .unavailable: return Theme.textSecondary
        }
    }
}

/// 下钻浮层：30 分钟图 + 结论 + 近两日买卖点。
///
/// 用独立的 ChanViewModel 拉 30 分钟分析，不改动详情页的日线状态；
/// 最近 2 个交易日（次级别判断所看的区间）用浅色底标出，与日线图上的标注对应。
struct SubLevelSheet: View {
    @ObservedObject var parent: ChanViewModel
    let sub: SubLevel

    @StateObject private var vm30 = ChanViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    chart
                    if !sub.recentSignals.isEmpty { signals }
                    Button {
                        dismiss()
                        Task { await parent.switchFreq("30min") }
                    } label: {
                        Label(L("切换到 30 分钟完整分析"), systemImage: "chart.xyaxis.line")
                            .font(AnalysisType.label)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .tint(Theme.accent)
                    Text(L("日线定方向、30 分钟找进出点：两者同向为共振，反向多为次级别的反弹或回调。"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, Theme.contentHInset + 8)
                .padding(.vertical, 12)
            }
            .background(Theme.background)
            .navigationTitle(parent.symbol.uppercased() + " · " + L("30分钟"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
        .presentationDetents([.fraction(0.72), .large])
        .presentationDragIndicator(.visible)
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                VerdictBadge(sub: sub)
                Text(L("日线：") + sub.dailyBiasLabel)
                    .font(.footnote)
                    .foregroundColor(SignalFormatting.biasColor(sub.dailyBias))
            }
            Text(sub.detail)
                .font(AnalysisType.body)
                .foregroundColor(Theme.textPrimary)
                .lineSpacing(AnalysisType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var chart: some View {
        if let a = vm30.analysis {
            VStack(alignment: .leading, spacing: 6) {
                ChanChartView(analysis: a, vm: vm30,
                              initialWindow: Self.window(for: a),
                              priceHeight: 220, macdHeight: 60,
                              highlightFrom: Self.lastSessionsStart(a, sessions: 2))
                Text(L("浅色底 = 最近 2 个交易日（次级别判断所看的区间）"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        } else if let err = vm30.errorMessage {
            Text(err)
                .font(.footnote)
                .foregroundColor(Theme.textSecondary)
                .frame(maxWidth: .infinity, minHeight: 120)
        } else {
            ProgressView()
                .frame(maxWidth: .infinity, minHeight: 300)
        }
    }

    private var signals: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("30 分钟近两日买卖点"))
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
            ForEach(sub.recentSignals) { sig in
                HStack(spacing: 8) {
                    Text(sig.label)
                        .font(AnalysisType.label)
                        .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
                    Text(sig.time)
                        .font(.footnote.monospacedDigit())
                        .foregroundColor(Theme.textSecondary)
                    Spacer(minLength: 4)
                    Text(String(format: "%.2f", sig.price))
                        .font(.footnote.monospacedDigit())
                        .foregroundColor(Theme.textPrimary)
                    Text(SignalFormatting.strengthLabel(sig.strength))
                        .font(.caption)
                        .foregroundColor(SignalFormatting.strengthColor(sig.strength))
                }
            }
        }
    }

    private func load() async {
        guard vm30.analysis == nil, !vm30.isLoading else { return }
        vm30.symbol = parent.symbol
        vm30.market = parent.market
        vm30.freq = "30min"
        vm30.startDate = parent.startDate
        vm30.endDate = parent.endDate
        await vm30.runAnalysis()
    }

    /// 默认看最新约 60 根（约 4~5 个交易日），给最近两日留出前文。
    static func window(for a: ChanAnalysis) -> ChartWindow {
        let count = Double(a.mergedCandles.count)
        let visible = min(60, max(10, count))
        return ChartWindow(firstVisible: max(0, count - visible), visibleCount: visible)
    }

    /// 最近 n 个交易日的起始日期（分钟线时间形如 "2026-09-23 10:30"，按日期部分去重）。
    static func lastSessionsStart(_ a: ChanAnalysis, sessions: Int) -> String? {
        var days: [String] = []
        for c in a.mergedCandles.reversed() {
            let day = String(c.time.prefix(10))
            if days.last != day { days.append(day) }
            if days.count == sessions { break }
        }
        return days.last
    }
}
