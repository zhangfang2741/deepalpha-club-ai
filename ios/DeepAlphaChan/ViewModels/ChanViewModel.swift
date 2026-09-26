import Foundation
import SwiftUI

/// 缠论页状态：管理查询参数、分析结果、GAP 任务轮询。
@MainActor
final class ChanViewModel: ObservableObject {
    // 查询参数
    @Published var symbol: String = "AAPL"
    /// 用户显式选择的市场。不靠代码形态猜——猜是能猜对，但 4~6 位数字在
    /// A 股和港股之间有歧义时，用户没有办法纠正。选了就以选的为准。
    @Published var market: StockMarket = .us
    @Published var freq: String = "daily"       // daily / weekly（30min 只在次级别浮层里用）

    /// 发给后端的代码：带上市场后缀，让服务端不必再猜。
    var requestSymbol: String {
        let raw = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !raw.isEmpty else { return raw }
        switch market {
        case .us: return raw
        case .cn: return raw.hasSuffix(".SS") || raw.hasSuffix(".SZ") ? raw : "\(raw).SS"
        case .hk: return raw.hasSuffix(".HK") ? raw : "\(raw).HK"
        }
    }
    @Published var startDate: Date
    @Published var endDate: Date

    /// 向前多取的 warmup 天数覆盖（nil=后端默认 180/540）。信号雷达点进详情时置 0，
    /// 让取数区间与雷达完全一致（雷达不额外加 warmup）。其他入口保持 nil。
    var warmupDays: Int?

    /// 当前标的的展示名称（如「中芯国际」）。仅在入口能提供真实名称时才有值
    /// （如从信号雷达点气泡进来）；手动输入代码等无名称的入口为 nil。加自选时
    /// 用它，拿不到就退回代码——避免自选里副标题原样重复代码。
    @Published var displayName: String?

    /// 雷达快照日期（`yyyy-MM-dd`），仅信号雷达点气泡进来时有值。ChanChartView
    /// 据此把可见窗口居中到这一天、并画一条竖线标出来，让用户看得出「分析的是
    /// 雷达上那一天」，而不是打开后默认停在最新数据。跟 warmupDays 同一个模式：
    /// 显式重置，不传则清空上一次雷达进来留下的值，避免串到后续手动分析上。
    var anchorDate: String?

    // 分析结果
    @Published var analysis: ChanAnalysis?
    @Published var isLoading = false
    @Published var errorMessage: String?

    // 次级别确认（日线定方向 × 30 分钟找买卖点）：日线分析成功后异步加载，
    // 不阻塞主结果；放在 VM 里而不是卡片自己持有，分享长图离屏渲染时也能拿到。
    @Published var subLevel: SubLevel?
    @Published var subLevelLoading = false
    /// 递增序号：切换标的/重新分析后，旧请求晚到的结果直接丢弃。
    private var subLevelRequestID = 0

    /// 次级别确认（30 分钟）是基础版起可用的付费功能（免费版不可用），由持有本 VM
    /// 的视图（通过 StoreManager.isSubscribed）同步。未订阅用户直接跳过请求——
    /// 省一次网络调用，也避免悄悄给未付费用户算出结果。
    var hasSubLevelAccess = false

    // 叠加图层开关
    @Published var showFractals = true
    @Published var showStrokes = true
    @Published var showSegments = true
    @Published var showPivots = true
    @Published var showSignals = true
    @Published var showDivergences = true

    // GAP 分析
    @Published var industryView: String = ""
    @Published var gapResult: StructureGapResult?
    @Published var gapLoading = false
    @Published var gapError: String?


    /// 记录上次校正日期时「今天」是哪天：ChanViewModel 是跨 Tab 共享的长生命周期对象
    /// （见类注释），startDate/endDate 只在 init 时按当时的 Date() 设一次。App 常驻
    /// 后台跨过零点不重启时，这两个日期会一直停在「昨天」，用户点「分析」实际请求的
    /// 截止日还是旧的——后端 canonical_end 只会把「比今天还晚」的日期拉回今天，比今天
    /// 早的（这正是这里的情况）照单全收，日线、次级别都会卡在旧的那天，表现为「明明是
    /// 25 号了，数据却停在 24 号」。
    private var lastKnownToday: Date

    init() {
        let now = Date()
        self.endDate = now
        self.lastKnownToday = now
        // 默认看最近约一年
        self.startDate = Calendar.current.date(byAdding: .day, value: -365, to: now) ?? now
    }

    /// 每次真正发起查询前调用：跨天了就把 start/end 一起顺移过去的天数，让「默认看到
    /// 今天」的窗口继续覆盖今天。只有 endDate 仍等于上次记录的「今天」（即用户没有手动
    /// 改过日期）才顺移——已经手动选了别的历史区间的保留用户的查询意图，不去动它。
    private func refreshDatesForNewDayIfNeeded() {
        let cal = Calendar.current
        let today = Date()
        guard !cal.isDate(lastKnownToday, inSameDayAs: today) else { return }
        if cal.isDate(endDate, inSameDayAs: lastKnownToday),
           let daysPassed = cal.dateComponents([.day], from: lastKnownToday, to: today).day,
           daysPassed > 0 {
            endDate = cal.date(byAdding: .day, value: daysPassed, to: endDate) ?? today
            startDate = cal.date(byAdding: .day, value: daysPassed, to: startDate) ?? startDate
        }
        lastKnownToday = today
    }

    // 按当前市场交易所时区换算（见 QueryDates）：A 股/港股盘中当天也能取到
    var startDateString: String { QueryDates.string(from: startDate, market: market.rawValue) }
    var endDateString: String { QueryDates.string(from: endDate, market: market.rawValue) }

    /// 一次套用一组查询条件，供「最近分析过」「起步示例」这类快捷入口使用。
    ///
    /// 市场和代码必须一起设：只改代码不改市场，点历史里的 AAPL 时会拿着当前
    /// 选中的 A 股去查一个美股代码。同理，任何「市场变了就清空代码」的联动都
    /// 不能挂在 `market` 的数据变化上，否则会把这里刚设好的代码清掉
    /// （见 QueryBar.marketBinding）。
    /// name 只在入口能提供真实名称时传（如信号雷达气泡）；不传则清空 displayName，
    /// 避免沿用上一只标的的名称串到这一只上。
    /// startDate/endDate/freq 可选：信号雷达点气泡进来时会传入与雷达同口径的窗口，
    /// 让详情页跑出的买卖点与雷达一致（否则默认 365 天窗口会算出不同结构）。不传则沿用当前值。
    func apply(
        market: StockMarket, symbol: String, name: String? = nil,
        startDate: Date? = nil, endDate: Date? = nil, freq: String? = nil,
        warmupDays: Int? = nil, anchorDate: String? = nil
    ) {
        self.market = market
        self.symbol = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        let trimmed = name?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.displayName = (trimmed?.isEmpty == false) ? trimmed : nil
        if let startDate { self.startDate = startDate }
        if let endDate { self.endDate = endDate }
        if let freq { self.freq = freq }
        // 显式重置：从雷达进来带 0，其他入口传 nil 时要清掉上一次雷达留下的 0，
        // 否则分析 Tab 会一直沿用「不加 warmup」，左边界结构可能漂移。
        self.warmupDays = warmupDays
        // 同理显式重置：不传则清掉上一次雷达进来留下的锚点日期。
        self.anchorDate = anchorDate
    }

    // MARK: - 缠论分析

    func runAnalysis() async {
        let sym = requestSymbol
        guard !sym.isEmpty else {
            errorMessage = L("请输入股票代码")
            return
        }
        refreshDatesForNewDayIfNeeded()
        isLoading = true
        errorMessage = nil
        // warmup 覆盖是「一次性」的：消费掉即清空，避免雷达带来的 warmup=0 泄漏到
        // 分析 Tab 后续手动分析（那会让普通 365 天分析少了左侧 warmup、结构可能漂移）。
        let warmup = warmupDays
        warmupDays = nil
        defer { isLoading = false }
        do {
            analysis = try await ChanService.analysis(
                symbol: sym, startDate: startDateString,
                endDate: endDateString, freq: freq, warmupDays: warmup)
            SKAdNetworkAttribution.report(.usedAnalysis)
            loadSubLevel(symbol: sym, warmupDays: warmup)
        } catch let error as APIError {
            // 失败时保留上一次结果，仅提示错误，避免清空已呈现的图表
            errorMessage = error.message
        } catch {
            errorMessage = L("分析失败，请稍后再试")
        }
    }

    // MARK: - 周期文案

    /// 周期的展示文案，标题与全屏页共用。
    static func freqLabel(_ freq: String) -> String {
        switch freq {
        case "weekly": return L("周线")
        case "30min": return L("30分钟")
        default: return L("日线")
        }
    }

    // MARK: - 次级别确认

    /// 从付费墙升级到高级版后调用：若当前已有分析结果但次级别此前因未订阅被跳过，
    /// 补一次请求，不用用户手动重新分析一遍。非日线/周线周期或本来就没有分析结果
    /// 时 `loadSubLevel` 内部的 guard 自然是空操作。
    func refreshSubLevelIfEligible() {
        guard analysis != nil, subLevel == nil, !subLevelLoading else { return }
        loadSubLevel(symbol: requestSymbol, warmupDays: nil)
    }

    /// 次级别逐级递推不跨级：日线配 30 分钟、周线配日线。失败只清空提示，不打扰主结果。
    private func loadSubLevel(symbol: String, warmupDays: Int?) {
        subLevelRequestID += 1
        let requestID = subLevelRequestID
        subLevel = nil
        guard hasSubLevelAccess, freq == "daily" || freq == "weekly" else {
            subLevelLoading = false
            return
        }
        subLevelLoading = true
        let start = startDateString, end = endDateString, parent = freq
        Task { [weak self] in
            let result = try? await ChanService.subLevel(
                symbol: symbol, startDate: start, endDate: end, parentFreq: parent, warmupDays: warmupDays)
            guard let self, requestID == self.subLevelRequestID else { return }
            self.subLevel = result
            self.subLevelLoading = false
        }
    }

    // MARK: - GAP 分析（异步任务 + 轮询）

    func runGapAnalysis() async {
        let view = industryView.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !view.isEmpty else {
            gapError = "请先填写你对该标的的产业结构判断"
            return
        }
        gapLoading = true
        gapError = nil
        gapResult = nil
        defer { gapLoading = false }
        do {
            let submitted = try await ChanService.submitGap(
                symbol: requestSymbol, startDate: startDateString,
                endDate: endDateString, industryView: view, freq: freq)
            try await pollGap(jobId: submitted.jobId)
        } catch let error as APIError {
            gapError = error.message
        } catch {
            gapError = "GAP 分析失败，请稍后再试"
        }
    }

    /// 轮询直到 done/failed，最多约 90 秒。
    private func pollGap(jobId: String) async throws {
        for _ in 0..<45 {
            try await Task.sleep(nanoseconds: 2_000_000_000)  // 2s
            let status = try await ChanService.gapStatus(jobId: jobId)
            switch status.status {
            case .done:
                gapResult = status.result
                return
            case .failed:
                gapError = status.error ?? "GAP 分析失败"
                return
            case .pending:
                continue
            }
        }
        gapError = "分析超时，请稍后重试"
    }
}
