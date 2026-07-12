import Foundation
import SwiftUI

/// 缠论页状态：管理查询参数、分析结果、GAP 任务轮询。
@MainActor
final class ChanViewModel: ObservableObject {
    // 查询参数
    @Published var symbol: String = "AAPL"
    @Published var freq: String = "daily"       // daily / weekly
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

    // MARK: - 缠论分析

    func runAnalysis() async {
        let sym = symbol.trimmingCharacters(in: .whitespaces)
        guard !sym.isEmpty else {
            errorMessage = "请输入股票代码"
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
            errorMessage = "分析失败，请稍后再试"
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
                symbol: symbol, startDate: startDateString,
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
