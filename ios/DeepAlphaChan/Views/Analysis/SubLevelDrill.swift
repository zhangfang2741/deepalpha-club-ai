import SwiftUI

/// 次级别下钻入口：紧贴图表下方的一行结论（「30分 共振买 · 日线偏多 ›」）。
///
/// 交互取缠论「区间套」的思路，级别逐级递推不跨级——日线配 30 分钟、周线配日线：
/// 结论贴着图表放，看完图紧接着就能看到次级别结论；点一下从底部弹出次级别图（半屏，可上拉全屏），
/// 大级别页原样不动、不重新加载。次级别图只从这里看，不单独提供 30 分钟入口。
/// 加载失败或后端未部署该接口时整行不出现，不打扰主结果。
struct SubLevelBar: View {
    @ObservedObject var vm: ChanViewModel
    /// 离屏渲染分享长图时置 true：保留结论，去掉点击。
    var isStatic = false

    @EnvironmentObject private var store: StoreManager
    @State private var showSheet = false
    /// 次级别确认是基础版起可用的付费功能，未订阅时点锁定行弹这个付费墙。
    @State private var showPaywall = false

    var body: some View {
        Group {
            if vm.freq == "daily" || vm.freq == "weekly" {
                if let sub = vm.subLevel {
                    Button { showSheet = true } label: { row(sub) }
                        .buttonStyle(.plain)
                        .allowsHitTesting(!isStatic)
                        .accessibilityHint(L("打开次级别图表"))
                        .sheet(isPresented: $showSheet) {
                            SubLevelSheet(parent: vm, sub: sub)
                        }
                // `!isStatic` 放在 `&&` 左边：短路求值保证离屏分享长图渲染
                // （PageSnapshot.render 走独立的 ImageRenderer，不继承 App 根部注入的
                // EnvironmentObject）时压根不会去读 store，避免「找不到 StoreManager」崩溃。
                } else if !isStatic && !store.isPremium {
                    // 非高级版：ChanViewModel 根本没发次级别请求（见 loadSubLevel 的
                    // hasSubLevelAccess 门禁），这里直接展示锁定态引导订阅，不误显示成加载中。
                    Button { showPaywall = true } label: { lockedRow }
                        .buttonStyle(.plain)
                        .accessibilityHint(L("订阅高级版解锁次级别确认"))
                        .sheet(isPresented: $showPaywall) { PaywallView() }
                } else if !isStatic && vm.subLevelLoading {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.mini)
                        Text(L("正在加载次级别…"))
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
        // 付费墙里升级高级版后，若之前因档位不够被跳过次级别请求，立刻补一次。三元表达式
        // 短路：isStatic 时右边的 store.isPremium 根本不求值，原因同上。
        .onChange(of: isStatic ? false : store.isPremium) { _, isPremium in
            if isPremium { vm.refreshSubLevelIfEligible() }
        }
    }

    private var lockedRow: some View {
        HStack(spacing: 8) {
            Image(systemName: "lock.fill")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.segment)
            Text(L("次级别确认 · 高级版解锁"))
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
            Spacer(minLength: 4)
            Image(systemName: "chevron.right")
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
        }
        .padding(.horizontal, 12)
        .frame(minHeight: 36)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
        .contentShape(Rectangle())
    }

    static func shortBias(_ bias: String, parent: String) -> String {
        let weekly = parent == "weekly"
        switch bias {
        case "bullish": return weekly ? L("周线偏多") : L("日线偏多")
        case "bearish": return weekly ? L("周线偏空") : L("日线偏空")
        default: return weekly ? L("周线中性") : L("日线中性")
        }
    }

    /// 次级别短名：30min → 「30分」，daily → 「日线」。
    static func childShort(_ subFreq: String) -> String {
        subFreq == "daily" ? L("日线") : L("30分")
    }

        private func row(_ sub: SubLevel) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "scope")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.accent)
            Text(Self.childShort(sub.subFreq))
                .font(.caption.weight(.semibold))
                .foregroundColor(Theme.textSecondary)
            VerdictBadge(sub: sub)
            // 一行放不下后端的完整方向描述，这里只给短标签；完整描述在浮层里
            Text(Self.shortBias(sub.dailyBias, parent: sub.parentFreq ?? "daily"))
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

/// 下钻浮层：次级别图 + 结论 + 近期买卖点。
///
/// 用独立的 ChanViewModel 拉次级别分析（日线页 → 30 分钟、周线页 → 日线），不改动
/// 详情页状态；次级别判断所看的近期区间（30 分钟近 2 个交易日 / 日线近两周）用浅色底
/// 标出，与大级别图上的标注对应。
struct SubLevelSheet: View {
    @ObservedObject var parent: ChanViewModel
    let sub: SubLevel

    @StateObject private var subVM = ChanViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    chart
                    if !sub.recentSignals.isEmpty { signals }
                    Text(isWeekly
                         ? L("周线定方向、日线找进出点：两者同向为共振，反向多为次级别的反弹或回调。")
                         : L("日线定方向、30 分钟找进出点：两者同向为共振，反向多为次级别的反弹或回调。"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, Theme.contentHInset + 8)
                .padding(.vertical, 12)
            }
            .background(Theme.background)
            .navigationTitle(parent.symbol.uppercased() + " · " + ChanViewModel.freqLabel(sub.subFreq))
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

    private var isWeekly: Bool { (sub.parentFreq ?? "daily") == "weekly" }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                VerdictBadge(sub: sub)
                Text((isWeekly ? L("周线：") : L("日线：")) + sub.dailyBiasLabel)
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
        if let a = subVM.analysis {
            VStack(alignment: .leading, spacing: 6) {
                ChanChartView(analysis: a, vm: subVM,
                              initialWindow: Self.window(for: a),
                              priceHeight: 220, macdHeight: 60,
                              highlightFrom: isWeekly ? Self.lastDaysStart(a, days: 14)
                                                      : Self.lastSessionsStart(a, sessions: 2))
                Text((isWeekly ? L("浅色底 = 最近两周（次级别判断所看的区间）")
                               : L("浅色底 = 最近 2 个交易日（次级别判断所看的区间）"))
                     + (a.mergedCandles.last.map { " · " + L("数据截至 %@", $0.displayTime) } ?? ""))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        } else if let err = subVM.errorMessage {
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
            Text(isWeekly ? L("日线近两周买卖点") : L("30 分钟近两日买卖点"))
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
                        .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
                }
            }
        }
    }

    private func load() async {
        guard subVM.analysis == nil, !subVM.isLoading else { return }
        subVM.symbol = parent.symbol
        subVM.market = parent.market
        subVM.freq = sub.subFreq
        subVM.startDate = parent.startDate
        subVM.endDate = parent.endDate
        await subVM.runAnalysis()
    }

    /// 默认看最新约 60 根（30 分钟约 4~5 个交易日 / 日线约 3 个月），给最近区间留出前文。
    static func window(for a: ChanAnalysis) -> ChartWindow {
        let count = Double(a.mergedCandles.count)
        let visible = min(60, max(10, count))
        return ChartWindow(firstVisible: max(0, count - visible), visibleCount: visible)
    }

    /// 最近 n 个自然日的起始日期（日线次级别用，与后端「近两周 = 14 个自然日」一致）。
    static func lastDaysStart(_ a: ChanAnalysis, days: Int) -> String? {
        guard let last = a.mergedCandles.last?.displayTime.prefix(10) else { return nil }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        guard let d = f.date(from: String(last)),
              let start = Calendar(identifier: .gregorian).date(byAdding: .day, value: -(days - 1), to: d)
        else { return nil }
        return f.string(from: start)
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
