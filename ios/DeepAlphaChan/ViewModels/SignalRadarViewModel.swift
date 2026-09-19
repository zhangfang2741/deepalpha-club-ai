import Foundation

/// 信号雷达状态：市场切换、拉取（含 generating 轮询）、日期选择。
@MainActor
final class SignalRadarViewModel: ObservableObject {
    @Published var market: StockMarket = .us
    @Published var response: SignalRadarResponse?
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading = false
    @Published var errorMessage: String?

    /// 首次扫描的 generating 轮询上限（次 × 间隔 ≈ 40s）。
    private let maxPolls = 16
    private let pollInterval: UInt64 = 2_500_000_000  // 2.5s

    /// 上次成功加载时的本地自然日（yyyy-MM-dd）。用来判断「跨天回到 Tab」是否要重拉：
    /// response 存在内存里，onAppear 原本只在 response==nil 时才拉，用户把 App 开着
    /// 过了一天再回来，最新日期就一直停在昨天。跨天则强制刷新。
    private var lastLoadedLocalDay: String?

    private static let localDayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    private var todayLocalDay: String { Self.localDayFormatter.string(from: Date()) }

    var days: [RadarDay] { response?.days ?? [] }

    var selectedDay: RadarDay? {
        guard !days.isEmpty else { return nil }
        let idx = min(max(selectedDayIndex, 0), days.count - 1)
        return days[idx]
    }

    /// 是否仍在首次扫描（后端 generating 且暂无数据）。
    var isScanning: Bool {
        isLoading || (response?.isGenerating ?? false && days.isEmpty)
    }

    func onAppear() {
        guard !isLoading else { return }
        // 首次进入（无数据）或已跨自然日（内存里的还是昨天的）都重拉，避免日期停住。
        if response == nil || lastLoadedLocalDay != todayLocalDay {
            Task { await load() }
        }
    }

    func switchMarket(_ m: StockMarket) {
        guard m != market else { return }
        market = m
        response = nil
        selectedDayIndex = 0
        Task { await load() }
    }

    func selectDay(_ index: Int) {
        selectedDayIndex = index
    }

    func refresh() async {
        await load(refresh: true)
    }

    func load(refresh: Bool = false) async {
        isLoading = true
        errorMessage = nil
        let requested = market
        do {
            var resp = try await SignalRadarService.fetch(market: requested.rawValue, refresh: refresh)
            var tries = 0
            while resp.isGenerating && tries < maxPolls {
                if market != requested { return }
                try await Task.sleep(nanoseconds: pollInterval)
                resp = try await SignalRadarService.fetch(market: requested.rawValue)
                tries += 1
            }
            if market != requested { return }
            response = resp
            selectedDayIndex = 0
            lastLoadedLocalDay = todayLocalDay
        } catch is CancellationError {
            return
        } catch let e as APIError {
            if market == requested { errorMessage = e.message }
        } catch {
            if market == requested { errorMessage = "加载失败，请稍后再试" }
        }
        if market == requested { isLoading = false }
    }
}
