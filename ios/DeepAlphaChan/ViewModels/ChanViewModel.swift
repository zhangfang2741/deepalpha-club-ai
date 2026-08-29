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
    @Published var freq: String = "daily"       // daily / weekly

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

    // 分析结果
    @Published var analysis: ChanAnalysis?
    @Published var isLoading = false
    @Published var errorMessage: String?

    // 叠加图层开关
    @Published var showFractals = true
    @Published var showStrokes = true
    @Published var showSegments = true
    @Published var showPivots = true
    @Published var showSignals = true

    // GAP 分析
    @Published var industryView: String = ""
    @Published var gapResult: StructureGapResult?
    @Published var gapLoading = false
    @Published var gapError: String?

    private let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "America/New_York")
        return f
    }()

    init() {
        let now = Date()
        self.endDate = now
        // 默认看最近约一年
        self.startDate = Calendar.current.date(byAdding: .day, value: -365, to: now) ?? now
    }

    var startDateString: String { dateFormatter.string(from: startDate) }
    var endDateString: String { dateFormatter.string(from: endDate) }

    /// 一次套用一组查询条件，供「最近分析过」「起步示例」这类快捷入口使用。
    ///
    /// 市场和代码必须一起设：只改代码不改市场，点历史里的 AAPL 时会拿着当前
    /// 选中的 A 股去查一个美股代码。同理，任何「市场变了就清空代码」的联动都
    /// 不能挂在 `market` 的数据变化上，否则会把这里刚设好的代码清掉
    /// （见 QueryBar.marketBinding）。
    func apply(market: StockMarket, symbol: String) {
        self.market = market
        self.symbol = symbol.trimmingCharacters(in: .whitespaces).uppercased()
    }

    // MARK: - 缠论分析

    func runAnalysis() async {
        let sym = requestSymbol
        guard !sym.isEmpty else {
            errorMessage = L("请输入股票代码")
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            analysis = try await ChanService.analysis(
                symbol: sym, startDate: startDateString,
                endDate: endDateString, freq: freq)
        } catch let error as APIError {
            // 失败时保留上一次结果，仅提示错误，避免清空已呈现的图表
            errorMessage = error.message
        } catch {
            errorMessage = L("分析失败，请稍后再试")
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
