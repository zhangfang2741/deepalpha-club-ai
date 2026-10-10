import Foundation

/// 信号雷达状态：市场切换、拉取（含 generating 轮询）、日期选择。
@MainActor
final class SignalRadarViewModel: ObservableObject {
    init() { observeModeChanges() }

    deinit { if let modeObserver { NotificationCenter.default.removeObserver(modeObserver) } }

    @Published var market: StockMarket = .us
    @Published var response: SignalRadarResponse?
    @Published var selectedDayIndex: Int = 0
    @Published var isLoading = false
    /// 静默更新拖过 1.5 秒才为真：雷达角上的「更新中」提示用它，而不是 isReloading（后者一开始请求就为真，会一闪而过）。
    @Published private(set) var showsUpdatingHint = false
    /// 后端真的在扫描（接口回 generating）。只有这时才写「正在扫描」；普通加载（缓存命中、通常 1 秒内）写「正在加载」，别让人以为每次都在重新算。
    @Published private(set) var backendScanning = false
    @Published var errorMessage: String?

    /// 免费预览锚定日期（「上个月 1 号」）的真实快照，未订阅会员时插到 `days`
    /// 最前面并默认选中，让日期轨在真实滚动窗口之外多出这一天可点；订阅会员则
    /// 完全不拉、不插——雷达图标是和会员完全一样的一套 UI，唯一区别是免费用户默认
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
    /// 带口径：切口径后示例日要按新口径重拉。
    var demoKey: String { "\(market.rawValue)|\(currentUniverse ?? "")|\(mode)" }

    /// 当前买卖点口径（strict / medium / loose），用户在雷达右上角切换；网络层读 `SignalMode.current()`，两边同步。
    @Published private(set) var mode: String = SignalMode.current()

    /// 已放弃拉取预览日的键（失败 / 轮询用尽仍在算 / 返回为空）。被取消不算放弃。
    @Published private(set) var demoGaveUpKey: String?
    /// 非会员等示例日等了超过 demoWaitSeconds 仍没到：不再让整页卡在「正在扫描」，先展示真实数据，示例日到了再并进来
    @Published private(set) var demoWaitExpiredKey: String?
    /// 示例日最多等这么久（缓存命中通常 1 秒内；冷启动要算几分钟，不能让用户干等；等得太短会先放出真实最新一天、示例日到了再跳回去，画面变两次）
    static let demoWaitSeconds: UInt64 = 10

    /// 未订阅且当前市场/指数的预览日还没到：这段时间不展示真实滚动窗口，否则会先闪出
    /// 最新一天的气泡、预览日到了再跳过去。
    ///
    /// 按「还没拿到、也没放弃」判断，而不是「请求是否在飞」：切市场后的第一帧请求还没发出，
    /// 按后者会先闪一下旧气泡调暗 +「正在刷新」，紧接着又换成「正在扫描」，两条提示前后
    /// 叠着出现。放弃后回落为 false，退回展示真实窗口（最新一天点不开，但至少不是空页）。
    var isAwaitingDemo: Bool {
        !isPremiumUser && demoDay == nil && demoGaveUpKey != demoKey && demoWaitExpiredKey != demoKey
    }

    /// 订阅层级由外部（持有本 VM 的 View）按 StoreManager 同步，VM 本身不感知
    /// StoreKit——跟 ChanViewModel.hasSubLevelAccess 同一个模式。非会员时：
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

    /// 每个市场记住上次选的 universe 键（nil=该市场默认大盘宽基指数）。切市场时各自恢复，
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
    ///
    /// 切市场期间 response 还是上一个市场的，不能用它的 universe；这时取该市场记住的选择，
    /// 没选过就取该市场默认指数（列表缓存里的 isDefault，或 defaultUniverseKeys 兜底）。
    var activeUniverseKey: String {
        if let pendingUniverseKey { return pendingUniverseKey }
        if let response, response.market == market.rawValue { return response.universe }
        return currentUniverse
            ?? availableUniverses.first(where: \.isDefault)?.key
            ?? Self.defaultUniverseKeys[market] ?? ""
    }

    /// 当前指数展示名：优先从列表里按高亮键取（计算中 response 为 nil 时也有名字），否则退回响应里的 etf_name。
    /// 顶部市场分段条（已选中那一段下面的小字）与雷达页的扫描提示共用。
    var activeUniverseName: String {
        if trendMode { return L("基本面动向") }
        if let u = availableUniverses.first(where: { $0.key == activeUniverseKey }) { return u.displayName }
        if activeUniverseKey == RadarUniverse.watchlistKey { return L("自选") }
        // 切市场时 response 暂时还是上一个市场的（保留旧内容防跳动），它的名称不能拿来用，
        // 否则选了 A 股却显示「正在扫描纳斯达克100」。还没拿到过这个市场的列表时用默认
        // 指数名兜底，直接显示「沪深300」，不先闪一下「A 股」。
        if let response, response.market == market.rawValue { return L(response.etfName) }
        if activeUniverseKey == Self.defaultUniverseKeys[market] { return Self.defaultUniverseNames[market] ?? "" }
        return ""
    }

    /// 各市场默认指数（与后端 universe.py 的 is_default 一致），只用于「从没进过这个市场、
    /// 还没拿到列表」时的展示兜底——切到 A 股直接显示「沪深300」，不先闪「A 股」。
    static let defaultUniverseKeys: [StockMarket: String] = [.us: "sp500", .cn: "csi300", .hk: "hsi"]
    static var defaultUniverseNames: [StockMarket: String] {
        [.us: L("标普500"), .cn: L("沪深300"), .hk: L("恒生指数")]
    }

    /// 每个市场拿到过的 universe 列表：切回来时直接恢复，切换器和扫描提示都不用等接口。
    private var universesByMarket: [StockMarket: [RadarUniverse]] = [:]

    /// 内存里的最近一次结果，按（市场, 指数, 口径）存：切市场 / 指数时先拿它立刻铺出气泡，
    /// 再后台静默更新（左上角「更新中」），不再每次都整页「正在扫描」干等接口。
    /// 只存 ready 的响应；进程内有效，退出 App 即清空（磁盘上的缓存不做，免得显示隔夜旧数据）。
    private var snapshotCache: [String: (resp: SignalRadarResponse, at: Date)] = [:]

    /// 内存缓存在这么久之内视为新鲜：切回去直接用、不再请求（后端快照一天才换一次，次级别 30 分钟一轮，与之对齐）。
    private static let snapshotFreshSeconds: TimeInterval = 1800

    private func snapshotKey(_ market: StockMarket, _ universe: String) -> String {
        "\(market.rawValue)|\(universe)|\(SignalMode.current())"
    }

    /// 内存里的上次结果；没有就读磁盘（上次打开 App 时存的），读到的放回内存。
    private func cachedEntry(_ m: StockMarket, _ universe: String) -> (resp: SignalRadarResponse, at: Date)? {
        let k = snapshotKey(m, universe)
        if let e = snapshotCache[k] { return e }
        guard universe != RadarUniverse.watchlistKey,
              let (data, at) = RadarDiskCache.read(k),
              let r = try? JSONDecoder().decode(SignalRadarResponse.self, from: data),
              !r.isGenerating, !r.days.isEmpty else { return nil }
        snapshotCache[k] = (r, at)
        return (r, at)
    }

    /// 切换后若内存里有这个（市场, 指数, 口径）的上次结果，立刻当作当前 response。
    /// 返回 true = 结果还新鲜（30 分钟内），调用方不用再请求：切市场一次完成、不闪、不重排。
    /// 返回 false = 缓存有但偏旧（先显示、再静默更新）或根本没有。
    @discardableResult
    private func applyCachedSnapshot() -> Bool {
        guard let entry = cachedEntry(market, activeUniverseKey) else { return false }
        response = entry.resp
        // 指数列表跟着缓存一起恢复：缓存新鲜时不再请求接口，而 availableUniverses 只在接口返回时才会设——
        // 冷启动读磁盘缓存（universesByMarket 是空的）后，市场分段条的指数下拉就一直不出现（只有 1 个选项时不显示下拉）。
        if !entry.resp.universes.isEmpty {
            availableUniverses = entry.resp.universes
            universesByMarket[market] = entry.resp.universes
        }
        jumpToDemoDayIfPresent()
        guard Date().timeIntervalSince(entry.at) < Self.snapshotFreshSeconds else { return false }
        pendingUniverseKey = nil
        isLoading = false
        return true
    }

    /// 免费示例日的内存缓存（按 demoKey：市场 + 指数 + 口径）。切回去直接用、不再整页等示例日：
    /// 否则每次切市场都是「正在扫描」→ 先放出真实最新一天 → 示例日到了再跳回去，画面变两次。
    private var demoCache: [String: (day: RadarDay, computedAt: String?, at: Date)] = [:]

    /// 示例日：内存 → 磁盘（上次打开 App 时存的）。
    private func cachedDemo() -> (day: RadarDay, computedAt: String?, at: Date)? {
        if let e = demoCache[demoKey] { return e }
        let universe = currentUniverse ?? activeUniverseKey
        guard universe != RadarUniverse.watchlistKey,
              let (data, at) = RadarDiskCache.read("demo|\(market.rawValue)|\(universe)|\(mode)"),
              let r = try? JSONDecoder().decode(SignalRadarResponse.self, from: data),
              !r.isGenerating, let day = r.days.first else { return nil }
        let e = (day: day, computedAt: r.computedAt, at: at)
        demoCache[demoKey] = e
        return e
    }

    /// 切换（市场 / 指数 / 口径）后，把这个键的示例日从内存恢复出来；没有就清空，等 loadDemoDay 去拉。
    private func restoreDemoFromCache() {
        if let entry = cachedDemo() {
            demoDay = entry.day
            demoComputedAt = entry.computedAt
        } else {
            demoDay = nil
            demoComputedAt = nil
        }
    }

    /// 两份快照的气泡（每天在场的信号 + 待确认）是不是完全一样：一样的话，刷新只是更新角标 / 共振 / 补算数，
    /// 画面上气泡的位置和个数都不变，用户看不出有「换了一张图」，选中的日期也不该重置。
    private func sameBubbles(_ a: SignalRadarResponse?, _ b: SignalRadarResponse) -> Bool {
        guard let a, a.market == b.market, a.universe == b.universe, a.days.count == b.days.count else { return false }
        return zip(a.days, b.days).allSatisfy { x, y in
            x.date == y.date && x.signals.map(\.id) == y.signals.map(\.id)
                && x.candidates.map(\.id) == y.candidates.map(\.id)
        }
    }

    /// 两份快照是不是同一份（后端没有新数据）：是的话刷新结果不必替换界面，避免气泡白白重排、日期选择被重置。
    private func isSameSnapshot(_ a: SignalRadarResponse?, _ b: SignalRadarResponse) -> Bool {
        guard let a else { return false }
        return a.market == b.market && a.universe == b.universe && a.computedAt == b.computedAt
            && a.subLevelAsOf == b.subLevelAsOf && a.pendingSymbols == b.pendingSymbols
            && a.analystPending == b.analystPending && a.days.count == b.days.count
            && a.qualityThreshold == b.qualityThreshold && a.qualityGoodCount == b.qualityGoodCount
    }

    /// 真实滚动窗口本身就有的天数，不含 demoDay。
    private var realDays: [RadarDay] { responseMatchesSelection ? (response?.days ?? []) : [] }

    /// response 是否就是当前所选（市场, 指数）的数据。切市场/指数后新数据回来前，response
    /// 还是旧的：不能拿来展示（否则免费用户会把新市场的示例日和旧市场的真实日期拼在一条
    /// 日期轨上），也不算「刷新中」——这段时间统一显示「正在扫描」，只有一种加载态。
    private var responseMatchesSelection: Bool {
        guard let response, response.market == market.rawValue else { return false }
        return response.universe.isEmpty || response.universe == activeUniverseKey
    }

    /// 非会员且 demoDay 已就绪时，示例日放在最前面：这是免费用户唯一能点开的一天，
    /// 放第一格、默认选中，进页面直接看到它，不必先看最新一天再跳过去。
    /// 预览日还在路上时返回空（见 isAwaitingDemo），页面显示扫描中。
    ///
    /// 示例日是「上个月 1 号」，后端真实窗口有 30 个交易日，所以每个月的前几周（如 10 月初的 09-01）
    /// 这天本来就在真实数据里、排在第 20 来位——日期轨只摆前 10 格，示例日根本不在轨上，选中它之后
    /// 「更多」在屏幕外，整条轨一格都不高亮。这种情况不重复插入，而是把真实窗口里的这一天**挪到最前面**
    /// （展示的仍是真实数据）；窗口里没有它时才把 demoDay 插到最前面。
    var days: [RadarDay] {
        if isAwaitingDemo { return [] }
        guard !isPremiumUser, let demoDay else { return realDays }
        guard let i = realDays.firstIndex(where: { $0.date == demoDay.date }) else {
            return [demoDay] + realDays
        }
        var out = realDays
        let day = out.remove(at: i)
        return [day] + out
    }

    /// 日期轨上选中的那一天（未经行业筛选）。
    var baseSelectedDay: RadarDay? {
        guard !days.isEmpty else { return nil }
        let idx = min(max(selectedDayIndex, 0), days.count - 1)
        return days[idx]
    }

    /// 雷达展示的那一天（后端已按出现时间从新到旧排好）；选了行业时只留该行业的信号。
    var selectedDay: RadarDay? {
        guard let day = baseSelectedDay else { return nil }
        guard let key = sectorFilter, day.hasSectorData else { return day }
        return day.filtered(sector: key)
    }

    /// 顶部「行业」的筛选：nil = 全部行业（默认）。切市场 / 指数时回到全部行业。
    @Published private(set) var sectorFilter: String?

    /// 用户在行业面板里选：nil = 全部行业。
    func setSectorFilter(_ key: String?) {
        guard key != sectorFilter else { return }
        sectorFilter = key
    }

    // MARK: - 行业强弱（扇区雷达的角度顺序、行业面板）

    /// 各日行业强弱（GET /macro/{market}/sectors?date=），键为「市场|日期」。
    @Published private(set) var sectorBoards: [String: SectorBoard] = [:]
    private var loadingSectorBoardKeys: Set<String> = []

    /// 选中日需要行业强弱时的「市场|日期」键（这一天有行业统计才要），否则 nil。View 用它驱动取数。
    var sectorBoardKey: String? {
        guard let day = baseSelectedDay, day.sectorRailReady else { return nil }
        return "\(market.rawValue)|\(day.date)"
    }

    /// 取选中日的行业强弱（雷达翻到哪天、筛选条就按哪天收盘排序）。失败不记，换天再回来会重试。
    func loadSectorBoardIfNeeded() async {
        guard let key = sectorBoardKey, let day = baseSelectedDay,
              sectorBoards[key] == nil, !loadingSectorBoardKeys.contains(key) else { return }
        loadingSectorBoardKeys.insert(key)
        defer { loadingSectorBoardKeys.remove(key) }
        // 请求放进独立的 Task，不跟调用方（.task(id:)）一起被取消：页面刷新时 .task 会被取消再重启，
        // 重启那次看到 key 还在 loading 就直接返回；若请求随第一次一起被取消，结果丢了又没人重试，
        // 行业横条会一直停在「数据准备中」（免费用户的示例日实测必现）。
        let market = market, date = day.date
        let board = await Task { try? await MarketOverviewService.sectors(market: market, date: date) }.value
        if let board, board.available {
            sectorBoards[key] = board
        }
    }

    /// 选中日的行业强弱表（还没取到 / 这一天没有行业统计时为 nil）。
    var selectedSectorBoard: SectorBoard? {
        sectorBoardKey.flatMap { sectorBoards[$0] }
    }

    /// 选中日行业从强到弱的 key（扇区雷达按这个顺序从上往下摆）；强弱还没取到时为空，
    /// 扇区按信号出现的先后排，取到后自动重排。
    var sectorOrder: [String] {
        (selectedSectorBoard?.sectors ?? [])
            .sorted { ($0.rsVsMarket ?? -.infinity) > ($1.rsVsMarket ?? -.infinity) }
            .map(\.key)
    }

    /// 行业 key → 展示名：优先用强弱表里后端给的名字，没有时用本地目录。
    func sectorName(_ key: String) -> String {
        if key == SectorRadarLayout.otherKey { return L("其它") }
        return selectedSectorBoard?.sectors.first(where: { $0.key == key })?.name ?? RadarSectorCatalog.name(key)
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

    /// 数据到位（真实响应或 demoDay 任一更新）后，非会员就把选中日跳回 demoDay，
    /// 不停在真实滚动窗口的「今天」——那天点不开，停在那没意义。已经选中 demoDay
    /// 或它还没加载出来时不做任何事。
    private func jumpToDemoDayIfPresent() {
        guard !isPremiumUser, let demoDay else { return }
        if let idx = days.firstIndex(where: { $0.date == demoDay.date }) {
            selectedDayIndex = idx
        }
    }

    /// 整页「正在扫描」：当前所选（市场, 指数）还没有任何可展示的数据时出现——首次进入、
    /// 切市场/指数（旧数据不再展示，见 responseMatchesSelection）、未订阅用户等示例日。
    var isScanning: Bool { (isLoading || isAwaitingDemo) && days.isEmpty }

    /// 只用于同一（市场, 指数）的重新加载（如手动刷新）：旧气泡调暗、暂不响应点按。
    /// 首次进入时示例日往往先于主数据返回，那时 response 还是 nil，不算刷新——否则扫描
    /// 结束后会再闪一下刷新态，看起来像两层加载。
    var isReloading: Bool { isLoading && responseMatchesSelection && !days.isEmpty }

    /// 轮询已用尽但后端仍在算（generating + 无数据、且当前没在轮询）。此时不干等，
    /// 前端展示「后台计算中，可稍后重试」——后台扫描会跑完并写缓存，重试即命中。
    var isComputingInBackground: Bool {
        !isLoading && (response?.isGenerating ?? false) && days.isEmpty
    }

    func onAppear() {
        guard !isLoading else { return }
        // 冷启动：先拿磁盘里上次的结果顶上（示例日也是），新鲜（30 分钟内）就不用请求；否则先显示、再静默更新
        if response == nil {
            restoreDemoFromCache()
            if applyCachedSnapshot() {
                lastLoadedLocalDay = todayLocalDay
                return
            }
        }
        // 首次进入（无数据）或已跨自然日（内存里的还是昨天的）都重拉，避免日期停住。
        if response == nil || lastLoadedLocalDay != todayLocalDay {
            Task { await load() }
        }
    }

    func switchMarket(_ m: StockMarket) {
        guard m != market else { return }
        market = m
        sectorFilter = nil
        // 不清空 response：新市场数据回来前保留旧内容（调暗 + 加载指示），页面不跳动
        // 不同市场的 universe 列表不同：换成这个市场之前拿到过的列表（没有就先空着），
        // 切换器与「正在扫描 X」立刻显示正确的指数名，不用等接口。
        availableUniverses = universesByMarket[m] ?? []
        pendingUniverseKey = nil
        selectedDayIndex = 0
        // demoDay 是按市场拉的（见 loadDemoDay），不清掉的话新市场数据回来前会短暂
        // 把上一个市场的那天错误地拼进这个市场的日期轨——不同市场、不同股票，纯粹
        // 是错的，不能留着当占位。
        restoreDemoFromCache()
        if trendMode { Task { await loadTrend() } }
        if applyCachedSnapshot() { return }
        Task { await load() }
    }

    /// 切换当前市场的 universe（科技窄基 ↔ 大盘宽基）。key 与当前生效的相同则忽略。
    /// 注意不清空 availableUniverses：正在计算时切换器仍要在，方便随时切回别的指数。
    func switchUniverse(_ key: String) {
        if trendMode {
            trendMode = false            // 从「基本面动向」切回某个指数的缠论雷达
            if key == activeUniverseKey { return }
        }
        guard key != activeUniverseKey else { return }
        sectorFilter = nil
        universeByMarket[market] = key
        pendingUniverseKey = key
        selectedDayIndex = 0
        // 示例日按 universe 算，旧指数的那天不能留着拼进新指数的日期轨（同 switchMarket）
        restoreDemoFromCache()
        if applyCachedSnapshot() { return }
        Task { await load() }
    }

    // MARK: - 基本面动向雷达

    /// 指数下拉框里的「基本面动向」：打开后画布换成动向雷达（同一张画布、同一套圈与气泡），
    /// 数据来自 `/quant-research/{market}/trend-radar`，与缠论雷达的指数 / 日期无关；选回任一指数即退出。
    @Published private(set) var trendMode = false
    @Published private(set) var trend: QuantTrendRadar?
    @Published private(set) var trendLoading = false
    @Published private(set) var trendError: String?
    @Published var trendKind: QuantTrendKind = .estimates

    /// 当前类别的条目（后端已按圈、按幅度排好）。
    var trendItems: [QuantTrendItem] {
        guard let trend, trend.market == market.rawValue else { return [] }
        return trend.items.filter { $0.kind == trendKind.rawValue }
    }

    func enterTrend() {
        guard !trendMode else { return }
        trendMode = true
        Task { await loadTrend() }
    }

    func loadTrend() async {
        let m = market.rawValue
        if trend?.market != m { trend = nil }
        trendError = nil
        trendLoading = true
        defer { trendLoading = false }
        do {
            let fresh = try await QuantResearchService.trendRadar(market: m)
            guard m == market.rawValue else { return }   // 加载期间切了市场，丢弃旧结果
            trend = fresh
        } catch {
            guard m == market.rawValue else { return }
            trendError = error.localizedDescription
        }
    }

    /// 口径在「我的 → 买卖点口径」里被改了：雷达跟着切（不论雷达页当前是否可见）。
    private func observeModeChanges() {
        modeObserver = NotificationCenter.default.addObserver(
            forName: SignalMode.didChange, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in
                guard let self, SignalMode.current() != self.mode else { return }
                self.switchMode(SignalMode.current())
            }
        }
    }
    private var modeObserver: NSObjectProtocol?

    /// 切换买卖点口径：旧口径的结果不能当新口径展示，先清掉（内存里有新口径的上次结果就直接用），再后台重拉。
    func switchMode(_ newMode: String) {
        guard newMode != mode, SignalMode.all.contains(newMode) else { return }
        mode = newMode            // 先改自己：下面 set 会发通知，观察者看到相同就不会再进来
        SignalMode.set(newMode)
        selectedDayIndex = 0
        pendingUniverseKey = nil
        restoreDemoFromCache()
        response = nil
        if applyCachedSnapshot() { return }
        Task { await load() }
    }

    func selectDay(_ index: Int) {
        selectedDayIndex = index
    }

    func refresh() async {
        await load(refresh: true)
    }

    /// 后台补算轮询间隔：后端每补完一轮（约 20～30 分钟）才重写快照，90 秒足够及时又不费流量。
    static let backfillPollSeconds: UInt64 = 90

    /// 后台还在补算（pendingSymbols > 0）时静默重拉缓存：补上的气泡与剩余只数随之更新。
    /// 不置 isLoading（不调暗、不打断浏览），不重置所选日期；只读缓存，不触发重新扫描。
    func refreshWhileBackfilling() async {
        guard !isLoading, responseMatchesSelection,
              (response?.pendingSymbols ?? 0) > 0 || (response?.analystPending ?? 0) > 0 else { return }
        let requested = market
        let requestedUniverse = currentUniverse
        guard let resp = try? await SignalRadarService.fetch(market: requested.rawValue, universe: requestedUniverse),
              !resp.isGenerating, !isLoading,
              market == requested, currentUniverse == requestedUniverse else { return }
        response = resp
        if selectedDayIndex >= days.count { selectedDayIndex = 0 }
    }

    func load(refresh: Bool = false) async {
        isLoading = true
        errorMessage = nil
        showsUpdatingHint = false
        backendScanning = false
        // 有旧气泡在显示时，静默更新 1.5 秒内不打扰；拖得久才在角上提示「更新中」（以前一闪而过很突兀）
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard let self, self.isLoading, self.isReloading else { return }
            self.showsUpdatingHint = true
        }
        let requested = market
        let requestedUniverse = currentUniverse
        let requestedMode = SignalMode.current()
        do {
            var resp = try await SignalRadarService.fetch(
                market: requested.rawValue, universe: requestedUniverse, refresh: refresh)
            var tries = 0
            var delay = pollInterval
            while resp.isGenerating && tries < maxPolls {
                if market != requested || currentUniverse != requestedUniverse || SignalMode.current() != requestedMode { return }
                backendScanning = true
                try await Task.sleep(nanoseconds: delay)
                resp = try await SignalRadarService.fetch(
                    market: requested.rawValue, universe: requestedUniverse)
                tries += 1
                delay = min(delay + 1_000_000_000, maxPollInterval)  // 每次 +1s，封顶 6s
            }
            // 加载期间用户切了市场或 universe，就丢弃这次结果，别覆盖新请求。
            if market != requested || currentUniverse != requestedUniverse || SignalMode.current() != requestedMode { return }
            // 后端没有新数据（同一份快照）：不替换界面，不重置日期选择，气泡不会白白重排一次
            // 气泡一样（只是角标 / 共振 / 补算数变了）也算没变：静默替换数据，但不重置日期选择、不跳
            let unchanged = responseMatchesSelection && (isSameSnapshot(response, resp) || sameBubbles(response, resp))
            if !unchanged || !isSameSnapshot(response, resp) { response = resp }
            if !resp.isGenerating, !resp.days.isEmpty {
                snapshotCache[snapshotKey(requested, resp.universe.isEmpty ? (requestedUniverse ?? activeUniverseKey) : resp.universe)] = (resp, Date())
            }
            if !resp.universes.isEmpty {
                availableUniverses = resp.universes
                universesByMarket[requested] = resp.universes
            }
            pendingUniverseKey = nil
            if !unchanged {
                selectedDayIndex = 0
                jumpToDemoDayIfPresent()
            }
            lastLoadedLocalDay = todayLocalDay
        } catch is CancellationError {
            return
        } catch let e as APIError {
            if market == requested && currentUniverse == requestedUniverse && SignalMode.current() == requestedMode { errorMessage = e.message }
        } catch {
            if market == requested && currentUniverse == requestedUniverse && SignalMode.current() == requestedMode {
                errorMessage = L("加载失败，请稍后再试")
            }
        }
        if market == requested && currentUniverse == requestedUniverse && SignalMode.current() == requestedMode {
            isLoading = false
            showsUpdatingHint = false
            backendScanning = false
        }
    }

    /// 拉「上个月 1 号」的免费预览快照（GET /signal-radar/demo），按当前（市场, universe），
    /// 仅未订阅会员时调用；由 `.task(id: demoKey)` 驱动，切市场/指数时 SwiftUI 自动
    /// 取消上一次未完成的调用、重新拉一次。轮询逻辑与 load() 同一套；轮询用尽仍在算就
    /// 安静放弃——不单独起一套「计算中」提示，日期轨里少这一天，之后重进页面再拉。
    func loadDemoDay() async {
        let key = demoKey
        let m = market
        // 自选是会员功能，没有免费预览；其余按所选指数（nil = 市场默认）
        let u = currentUniverse == RadarUniverse.watchlistKey ? nil : currentUniverse
        // 同一键已在拉（onChange 与 .task(id:) 可能同时触发）就不重复发请求。
        guard loadingDemoKey != key else { return }
        // 内存里的示例日还新鲜（30 分钟内，后端每天才换）：已经恢复出来了，不再请求
        if demoDay != nil, let entry = demoCache[key], Date().timeIntervalSince(entry.at) < Self.snapshotFreshSeconds { return }
        loadingDemoKey = key
        // 只清自己设的：切换后新请求已把它改成新键，旧请求收尾时不能把它清掉。
        defer { if loadingDemoKey == key { loadingDemoKey = nil } }
        // 等太久就先放真实数据出来（示例日之后到了再并进日期轨），不让整页卡在「正在扫描」
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: Self.demoWaitSeconds * 1_000_000_000)
            guard let self, self.demoDay == nil, self.demoKey == key, self.demoGaveUpKey != key else { return }
            self.demoWaitExpiredKey = key
        }
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
            guard demoKey == key else { return }
            guard !resp.isGenerating, let day = resp.days.first else {
                demoGaveUpKey = key  // 轮询用尽仍在算，或当天没有数据：放弃，退回真实窗口
                return
            }
            let same = demoDay.map { $0.date == day.date && $0.signals.map(\.id) == day.signals.map(\.id) } ?? false
            demoCache[key] = (day, resp.computedAt, Date())
            demoDay = day
            demoComputedAt = resp.computedAt
            if !same { jumpToDemoDayIfPresent() }
        } catch {
            // 被取消（切走了 / 页面消失）不算放弃，回来 .task 会重拉；真失败才放弃，
            // 退回真实滚动窗口的展示。URLSession 被取消抛的是 URLError，不是 CancellationError。
            if !Task.isCancelled, demoKey == key { demoGaveUpKey = key }
        }
    }
}
