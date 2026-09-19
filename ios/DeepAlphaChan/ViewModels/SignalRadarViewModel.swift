import Foundation

/// 信号雷达状态：市场切换、拉取（含 generating 轮询）、日期选择。
@MainActor
final class SignalRadarViewModel: ObservableObject {
    @Published var market: StockMarket = .us
    @Published var response: SignalRadarResponse?
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading = false
    @Published var errorMessage: String?

    /// generating 轮询：间隔从 2s 递增到 6s 封顶，最多 8 次（2+3+4+5+6+6+6+6 ≈ 38s）。
    /// 大盘宽基（标普500 等）首次全量扫描通常比这久——约 30~40s 后不再干等，转成「后台
    /// 计算中」态让用户重试（后台扫描会跑完并写缓存，重试即命中），见 isComputingInBackground。
    private let maxPolls = 8
    private let pollInterval: UInt64 = 2_000_000_000       // 起始 2s
    private let maxPollInterval: UInt64 = 6_000_000_000    // 封顶 6s

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

    /// 每个市场记住上次选的 universe 键（nil=该市场默认科技指数）。切市场时各自恢复，
    /// 不会把港股选的「恒生指数」带到美股上。
    private var universeByMarket: [StockMarket: String] = [:]

    /// 当前市场选中的 universe 键（nil=默认）。
    private var currentUniverse: String? { universeByMarket[market] }

    /// 该市场可选的 universe 列表（来自响应，默认在前）。只有 >1 个时前端才显示切换器。
    var universes: [RadarUniverse] { response?.universes ?? [] }

    /// 当前实际生效的 universe 键（用来在切换器里高亮；响应回来才确定）。
    var activeUniverseKey: String { response?.universe ?? "" }

    var days: [RadarDay] { response?.days ?? [] }

    var selectedDay: RadarDay? {
        guard !days.isEmpty else { return nil }
        let idx = min(max(selectedDayIndex, 0), days.count - 1)
        return days[idx]
    }

    /// 正在主动拉取/轮询（转圈扫描态）。
    var isScanning: Bool { isLoading }

    /// 轮询已用尽但后端仍在算（generating + 无数据、且当前没在轮询）。此时不干等，
    /// 前端展示「后台计算中，可稍后重试」——后台扫描会跑完并写缓存，重试即命中。
    var isComputingInBackground: Bool {
        !isLoading && (response?.isGenerating ?? false) && days.isEmpty
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

    /// 切换当前市场的 universe（科技窄基 ↔ 大盘宽基）。key 与当前生效的相同则忽略。
    func switchUniverse(_ key: String) {
        guard key != activeUniverseKey else { return }
        universeByMarket[market] = key
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
        let requestedUniverse = currentUniverse
        do {
            var resp = try await SignalRadarService.fetch(
                market: requested.rawValue, universe: requestedUniverse, refresh: refresh)
            var tries = 0
            var delay = pollInterval
            while resp.isGenerating && tries < maxPolls {
                if market != requested || currentUniverse != requestedUniverse { return }
                try await Task.sleep(nanoseconds: delay)
                resp = try await SignalRadarService.fetch(
                    market: requested.rawValue, universe: requestedUniverse)
                tries += 1
                delay = min(delay + 1_000_000_000, maxPollInterval)  // 每次 +1s，封顶 6s
            }
            // 加载期间用户切了市场或 universe，就丢弃这次结果，别覆盖新请求。
            if market != requested || currentUniverse != requestedUniverse { return }
            response = resp
            selectedDayIndex = 0
            lastLoadedLocalDay = todayLocalDay
        } catch is CancellationError {
            return
        } catch let e as APIError {
            if market == requested && currentUniverse == requestedUniverse { errorMessage = e.message }
        } catch {
            if market == requested && currentUniverse == requestedUniverse {
                errorMessage = "加载失败，请稍后再试"
            }
        }
        if market == requested && currentUniverse == requestedUniverse { isLoading = false }
    }
}
