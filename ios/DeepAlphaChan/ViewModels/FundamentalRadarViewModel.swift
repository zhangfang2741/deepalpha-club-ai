import Foundation

/// 雷达「基本面研究」tab 的数据：当前（市场, 指数）里综合等级最高的若干只股票。
/// 不按日期、没有日期轨；画布与缠论雷达共用同一套（多环 / 浮动动画 / 摆位），这里把榜单映射成 RadarDay + RadarSignal：
/// 环 = 综合等级段（A / B / C 及以下，越靠中心等级越高），气泡大小 / 深浅随等级，最后一行写等级字母；
/// 分析师评级只作角标（近 30 天券商净上调 ▲n / 净下调 ▼n，仅美股）。
@MainActor
final class FundamentalRadarViewModel: ObservableObject {
    @Published private(set) var response: FundamentalTopResponse?
    @Published private(set) var isLoading = false
    /// 已加载数据对应的 (市场, 指数)、当前请求的 (市场, 指数)、最近一次失败的范围：
    /// loaded ≠ requested = 刚切了市场 / 指数、旧数据不能再展示。
    @Published private(set) var loadedKey = ""
    @Published private(set) var requestedKey = ""
    @Published private(set) var failedKey = ""
    /// 顶部行业胶囊的筛选（nil = 全部行业）：与缠论雷达共用同一个行业键，只留该行业的股票。
    @Published var sectorFilter: String?

    /// 画布最多画几只（等级最高的在前），其余点「另有 N 个 · 查看全部」。
    static let bubbleLimit = 10
    /// 13 档字母等级，A+ 最高、F 最低（与后端 GRADE_ORDER 一致）。
    static let gradeOrder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
    /// 环文字（由内向外）。
    static var ringLabels: [String] { ["A", "B", L("C 及以下")] }

    static func scopeKey(market: String, universe: String?) -> String { "\(market)|\(universe ?? "")" }

    /// 只有响应与当前所选范围一致才展示；切市场 / 指数后旧数据不再显示（与缠论雷达同一规则）。
    var items: [FundamentalItem] { response != nil && loadedKey == requestedKey ? (response?.items ?? []) : [] }

    /// 套上行业筛选后的榜单（等级从高到低）。
    var filteredItems: [FundamentalItem] {
        guard let key = sectorFilter else { return items }
        return items.filter { ($0.sector ?? RadarDay.otherSectorKey) == key }
    }

    /// 整页「正在加载」：当前所选范围还没有可展示的数据（首次进入、切市场 / 指数）。
    var isScanning: Bool { isLoading && items.isEmpty }
    /// 同一范围重新加载：旧气泡调暗、暂不响应点按。
    var isReloading: Bool { isLoading && !items.isEmpty }
    /// 读取失败（接口报错，或后端说评级数据读取失败）。
    var hasError: Bool { failedKey == requestedKey || (loadedKey == requestedKey && response?.available == false) }
    /// 当前范围还没有可展示的数据：切换那一帧就为 true（不等 .task 起来、不依赖 isLoading），已失败的范围不算。
    func needsLoading(scope: String) -> Bool { loadedKey != scope && failedKey != scope }

    /// 分析师角标还在后台补的只数。
    var analystPending: Int { loadedKey == requestedKey ? (response?.analystPending ?? 0) : 0 }
    var analystSupported: Bool { response?.analystSupported ?? true }
    var asOf: String { response?.asOf ?? "" }
    var rated: Int { response?.rated ?? 0 }

    /// 超过 bubbleLimit 被折叠的只数。
    var hiddenCount: Int { max(0, filteredItems.count - Self.bubbleLimit) }

    /// 各行业在榜单里的只数（不受行业筛选影响；key 同缠论雷达，buy = 只数），给行业弹层用。
    var sectorCounts: [String: [String: Int]] {
        var out: [String: [String: Int]] = [:]
        for e in items { out[e.sector ?? RadarDay.otherSectorKey, default: [:]]["buy", default: 0] += 1 }
        return out
    }

    /// 交给雷达画布的「一天」：前 bubbleLimit 只。
    var radarDay: RadarDay? {
        let all = filteredItems
        guard response != nil, loadedKey == requestedKey else { return nil }
        return RadarDay(date: asOf, quantFilter: nil, buyCount: all.count, sellCount: 0,
                        signals: all.prefix(Self.bubbleLimit).map { Self.signal(from: $0) },
                        candidates: [], sectorCounts: nil)
    }

    /// 环：A 段 = 0、B 段 = 1、其余（C 及以下）= 2。
    static func ringBand(grade: String) -> Int {
        let idx = gradeOrder.firstIndex(of: grade) ?? (gradeOrder.count - 1)
        return idx <= 2 ? 0 : (idx <= 5 ? 1 : 2)
    }

    /// 气泡大小档（对应缠论一 / 二 / 三类的 58 / 72 / 86）：A+ 最大、A 段其余中、其余最小。
    static func sizeTier(grade: String) -> Int { grade == "A+" ? 3 : (ringBand(grade: grade) == 0 ? 2 : 1) }

    static func signal(from e: FundamentalItem) -> RadarSignal {
        // 榜单只陈列等级、没有买卖方向：统一用 buy 色（红）；颜色深浅随等级（A+ 最深）
        var s = RadarSignal(
            symbol: e.symbol, name: e.name, side: "buy", label: e.grade,
            signalType: "buy" + String(sizeTier(grade: e.grade)), date: e.asOf, price: 0,
            strength: 0.5, bias: "neutral",
            signalStrength: e.grade == "A+" ? "strong" : (ringBand(grade: e.grade) == 0 ? "medium" : "weak"),
            confirmed: true, pivotStageDepth: 0.5, subLevelVerdict: nil, subLevelLabel: nil,
            // 气泡最后一行（缠论气泡里放评级的那一行）写等级字母
            quantGrade: e.grade, quantScore: e.score, quantAsOf: e.asOf, quantStatus: nil,
            // 分圈：环 = 等级段（ringBand 0/1/2 → ageDays 0/1/4）
            ageDays: [0, 1, 4][ringBand(grade: e.grade)], sector: e.sector)
        s.analystMark = e.analystMark
        return s
    }

    // MARK: - 拉取

    func load(market: String, universe: String?, force: Bool = false) async {
        let key = Self.scopeKey(market: market, universe: universe)
        requestedKey = key
        if !force, key == loadedKey, response != nil { return }
        isLoading = true
        if failedKey == key { failedKey = "" }
        defer { if requestedKey == key { isLoading = false } }
        do {
            let resp = try await SignalRadarService.fundamentalTop(market: market, universe: universe)
            // 加载期间用户又切了市场 / 指数：丢弃这次结果，别覆盖新请求
            guard requestedKey == key else { return }
            loadedKey = key
            response = resp
        } catch {
            if Task.isCancelled || requestedKey != key { return }
            failedKey = key
        }
    }

    /// 后台还在补分析师角标（analystPending > 0）时每 20 秒静默重拉一次：不置 isLoading（不转圈、不调暗），
    /// 补上的角标直接出现；范围变了 / 任务取消即退出。
    func pollWhilePending(market: String, universe: String?) async {
        let key = Self.scopeKey(market: market, universe: universe)
        while !Task.isCancelled, requestedKey == key, analystPending > 0 {
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            guard !Task.isCancelled, requestedKey == key else { return }
            guard let resp = try? await SignalRadarService.fundamentalTop(market: market, universe: universe),
                  requestedKey == key else { continue }
            response = resp
        }
    }
}
