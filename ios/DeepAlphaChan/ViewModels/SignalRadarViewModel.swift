import Foundation

/// 信号雷达状态：市场切换、拉取（含 generating 轮询）、日期选择。
@MainActor
final class SignalRadarViewModel: ObservableObject {
    @Published var market: StockMarket = .us
    @Published var response: SignalRadarResponse?
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading = false
    @Published var errorMessage: String?

    /// 免费预览锚定日期（「上个月 1 号」）的真实快照，未订阅高级版时插到 `days`
    /// 最前面并默认选中，让日期轨在真实滚动窗口之外多出这一天可点；订阅高级版则
    /// 完全不拉、不插——雷达图标是和高级版完全一样的一套 UI，唯一区别是免费用户默认
    /// 停在这一天、点其它天会被拦下（见 SignalRadarView 的 dayChip/jumpToNearestDay
    /// 门禁），而不是另起一套「示例」界面。
    @Published private(set) var demoDay: RadarDay?
    /// demoDay 所属那次扫描的算出时刻（跟主 response 是两次不同的扫描，metaRow
    /// 展示「数据 XX:XX 计算」时要用对应那次的时刻，见 selectedDayComputedAtText）。
    private var demoComputedAt: String?
    /// 正在拉免费预览的（市场, universe）键。记键而不是一个布尔：切市场/指数时 `.task(id:)`
    /// 取消旧请求、立刻发新请求，旧请求的 defer 还没跑完——用布尔的话新请求会被 guard
    /// 当成「已在加载」直接跳过，新市场/指数就永远拿不到预览日。
    @Published private(set) var loadingDemoKey: String?

    /// 免费预览按（市场, universe）区分：同一市场切换纳斯达克100/标普500，示例日要跟着换。
    /// 也用作 View 里 `.task(id:)` 的 id。
    var demoKey: String { "\(market.rawValue)|\(currentUniverse ?? "")" }

    /// 未订阅且当前市场/指数的预览日还在路上：这段时间不展示真实滚动窗口，否则会先闪出
    /// 最新一天的气泡、预览日到了再跳过去。预览拉取失败/放弃后此值回落为 false，
    /// 退回展示真实窗口（最新一天点不开，但至少不是空页）。
    var isAwaitingDemo: Bool {
        !isPremiumUser && demoDay == nil && loadingDemoKey == demoKey
    }

    /// 订阅层级由外部（持有本 VM 的 View）按 StoreManager 同步，VM 本身不感知
    /// StoreKit——跟 ChanViewModel.hasSubLevelAccess 同一个模式。非高级版时：
    /// days 会把 demoDay 追加进来，且新数据到位时自动把选中日跳回 demoDay。
    var isPremiumUser: Bool = false {
        didSet {
            guard isPremiumUser != oldValue else { return }
            if isPremiumUser {
                // 升级后 demoDay 不再追加进 days，数组变短；不重置的话 selectedDayIndex
                // 停在原来的下标会被 selectedDay 的 clamp 顶到新数组的最后一个（=最旧的
                // 一个真实交易日），而不是「今天」，体验很怪——升级这一刻直接跳回今天。
                selectedDayIndex = 0
            } else {
                jumpToDemoDayIfPresent()
            }
        }
    }

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

    /// 该市场可选的 universe 列表（默认在前）。独立持有、不随「切换时清空 response」一起
    /// 消失——这样正在计算（转圈/后台计算卡片）时切换器依然在，用户随时能切回别的指数。
    /// 只在切「市场」时清空（不同市场列表不同），切「universe」时保留。
    @Published private(set) var availableUniverses: [RadarUniverse] = []
    var universes: [RadarUniverse] { availableUniverses }

    /// 正在切往的 universe 键（还没拉回结果时用于即时高亮）；结果落地后清空。
    private var pendingUniverseKey: String?

    /// 当前在切换器里高亮的 universe 键：优先目标键（切换瞬间就高亮），否则用响应里的。
    var activeUniverseKey: String { pendingUniverseKey ?? response?.universe ?? "" }

    /// 真实滚动窗口本身就有的天数，不含 demoDay。
    private var realDays: [RadarDay] { response?.days ?? [] }

    /// 非高级版且 demoDay 已就绪时，把它插到真实天数列表最前面：这是免费用户唯一
    /// 能点开的一天，放第一格、默认选中，进页面直接看到它，不必先看最新一天再跳过去。
    /// 预览日还在路上时返回空（见 isAwaitingDemo），页面显示扫描中。极少数情况下
    /// （如月初，真实窗口正好覆盖到了上个月 1 号）这天本来就在真实数据里，不重复
    /// 插入——直接展示真实数据，由 jumpToDemoDayIfPresent 选中它。
    var days: [RadarDay] {
        if isAwaitingDemo { return [] }
        guard !isPremiumUser, let demoDay, !realDays.contains(where: { $0.date == demoDay.date })
        else { return realDays }
        return [demoDay] + realDays
    }

    var selectedDay: RadarDay? {
        guard !days.isEmpty else { return nil }
        let idx = min(max(selectedDayIndex, 0), days.count - 1)
        return days[idx]
    }

    /// 免费预览锚定日期的字符串（未订阅时才有意义）；View 用它判断某个日期轨格子
    /// 是不是「唯一能点开的那天」，别的格子点了要弹付费墙。
    var unlockedDayDate: String? { isPremiumUser ? nil : demoDay?.date }

    /// 当前选中日是否为「追加」进来的免费预览日（而非真实滚动窗口本身就有的一天，
    /// 哪怕日期字符串凑巧相同）——只有真正追加的那天要用 demoComputedAt 展示
    /// 「数据 XX:XX 计算」，凑巧重叠的那天展示的就是真实数据，该用真实扫描的
    /// computedAt 才对。
    var selectedDayComputedAtText: String? {
        guard !isPremiumUser, let demoDay, selectedDay?.date == demoDay.date,
              !realDays.contains(where: { $0.date == demoDay.date })
        else { return response?.computedAtText }
        return Self.localTime(from: demoComputedAt)
    }

    private static func localTime(from raw: String?) -> String? {
        guard let raw, !raw.isEmpty, let date = ISO8601DateFormatter().date(from: raw) else { return nil }
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }

    /// 数据到位（真实响应或 demoDay 任一更新）后，非高级版就把选中日跳回 demoDay，
    /// 不停在真实滚动窗口的「今天」——那天点不开，停在那没意义。已经选中 demoDay
    /// 或它还没加载出来时不做任何事。
    private func jumpToDemoDayIfPresent() {
        guard !isPremiumUser, let demoDay else { return }
        if let idx = days.firstIndex(where: { $0.date == demoDay.date }) {
            selectedDayIndex = idx
        }
    }

    /// 正在主动拉取/轮询（转圈扫描态）。
    /// 整页「扫描中」只在确实还没有任何数据可展示时出现；已有数据时（切换市场、刷新）
    /// 保留旧内容、原地盖加载态，避免整块内容被替换导致页面上下跳动。
    /// 未订阅用户等预览日时也算扫描态，不先露出最新一天的气泡。
    var isScanning: Bool { (isLoading || isAwaitingDemo) && days.isEmpty }

    /// 已有内容、正在加载新数据（切换市场/universe、刷新）：旧内容调暗 + 加载指示，不换布局。
    var isReloading: Bool { isLoading && !days.isEmpty }

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
        // 不清空 response：新市场数据回来前保留旧内容（调暗 + 加载指示），页面不跳动
        // 不同市场的 universe 列表不同，清掉旧的，等新市场响应回来再填。
        availableUniverses = []
        pendingUniverseKey = nil
        selectedDayIndex = 0
        // demoDay 是按市场拉的（见 loadDemoDay），不清掉的话新市场数据回来前会短暂
        // 把上一个市场的那天错误地拼进这个市场的日期轨——不同市场、不同股票，纯粹
        // 是错的，不能留着当占位。
        demoDay = nil
        demoComputedAt = nil
        Task { await load() }
    }

    /// 切换当前市场的 universe（科技窄基 ↔ 大盘宽基）。key 与当前生效的相同则忽略。
    /// 注意不清空 availableUniverses：正在计算时切换器仍要在，方便随时切回别的指数。
    func switchUniverse(_ key: String) {
        guard key != activeUniverseKey else { return }
        universeByMarket[market] = key
        pendingUniverseKey = key
        selectedDayIndex = 0
        // 示例日按 universe 算，旧指数的那天不能留着拼进新指数的日期轨（同 switchMarket）
        demoDay = nil
        demoComputedAt = nil
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
            if !resp.universes.isEmpty { availableUniverses = resp.universes }
            pendingUniverseKey = nil
            selectedDayIndex = 0
            jumpToDemoDayIfPresent()
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

    /// 拉「上个月 1 号」的免费预览快照（GET /signal-radar/demo），按当前（市场, universe），
    /// 仅未订阅高级版时调用；由 `.task(id: demoKey)` 驱动，切市场/指数时 SwiftUI 自动
    /// 取消上一次未完成的调用、重新拉一次。轮询逻辑与 load() 同一套；轮询用尽仍在算就
    /// 安静放弃——不单独起一套「计算中」提示，日期轨里少这一天，之后重进页面再拉。
    func loadDemoDay() async {
        let key = demoKey
        let m = market
        // 自选是高级版功能，没有免费预览；其余按所选指数（nil = 市场默认）
        let u = currentUniverse == RadarUniverse.watchlistKey ? nil : currentUniverse
        // 同一键已在拉（onChange 与 .task(id:) 可能同时触发）就不重复发请求。
        guard loadingDemoKey != key else { return }
        loadingDemoKey = key
        // 只清自己设的：切换后新请求已把它改成新键，旧请求收尾时不能把它清掉。
        defer { if loadingDemoKey == key { loadingDemoKey = nil } }
        do {
            var resp = try await SignalRadarService.demo(market: m.rawValue, universe: u)
            var tries = 0
            var delay = pollInterval
            while resp.isGenerating && tries < maxPolls {
                try Task.checkCancellation()
                try await Task.sleep(nanoseconds: delay)
                resp = try await SignalRadarService.demo(market: m.rawValue, universe: u)
                tries += 1
                delay = min(delay + 1_000_000_000, maxPollInterval)
            }
            try Task.checkCancellation()
            guard demoKey == key, !resp.isGenerating, let day = resp.days.first else { return }
            demoDay = day
            demoComputedAt = resp.computedAt
            jumpToDemoDayIfPresent()
        } catch {
            // 免费预览拉取失败/取消：安静放弃，不影响真实滚动窗口的展示。
        }
    }
}
