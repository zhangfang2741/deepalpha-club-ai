import Foundation

/// 雷达「基本面研究」tab 的数据：当前（市场, 指数）最近几天综合等级升降事件。
/// 画布与缠论雷达共用同一套（多环 / 浮动动画 / 摆位），这里把「选中日的评级升降」映射成 RadarDay + RadarSignal：
/// 升档 = 买色（红）、降档 = 卖色（绿），颜色深浅与气泡大小随变档数，环 = 新等级（A / B / C 及以下）。
/// 两个事件 tab 共用同一套画布与 VM，只有数据来源与文案不同。
enum RadarEventKind {
    case grade     // 基本面研究：综合等级升 / 降
    case analyst   // 分析师评级：券商净上调 / 下调

    var tabTitle: String { self == .grade ? L("基本面研究") : L("分析师评级") }
    var upWord: String { self == .grade ? L("升档") : L("上调") }
    var downWord: String { self == .grade ? L("降档") : L("下调") }
    var summaryTitle: String { self == .grade ? L("%@ · 综合评级升降") : L("%@ · 分析师评级调整") }
    /// 环文字（由内向外）。
    var ringLabels: [String] {
        self == .grade ? ["A", "B", L("C 及以下")] : [L("买入"), L("中性"), L("卖出")]
    }
    /// 行业面板里的计数词与底部说明（说明带两个 %@：指数名、日期）。
    var sectorWords: (up: String, down: String, note: String) {
        self == .grade
            ? (L("升"), L("降"), L("升降档数为%@ %@ 的评级统计；点行业即在雷达上只看该行业。"))
            : (L("上调"), L("下调"), L("上调 / 下调家数为%@ %@ 的券商评级统计；点行业即在雷达上只看该行业。"))
    }
    var emptyDay: String { self == .grade ? L("当日无评级升降") : L("当日无评级调整") }
    var legendHint: String {
        self == .grade ? L("越靠中心评级越高 · 颜色越深、气泡越大变档越多")
                       : L("越靠中心评级越偏多 · 颜色越深、气泡越大净调整越多")
    }
    var disclaimer: String {
        self == .grade ? L("评级由量化指标计算，仅为孤立观测，不构成投资建议。")
                       : L("券商评级调整仅为孤立观测，不代表后续涨跌，不构成投资建议。")
    }
    var allTitle: String { self == .grade ? L("%@ 综合评级升降") : L("%@ 分析师评级调整") }
    var emptyMessage: String {
        self == .grade
            ? L("这个范围最近没有评级升降。评级历史需要至少两个评级日才能比较，刚上线的市场或节假日期间会暂时没有。")
            : L("这个范围最近没有券商评级调整。")
    }
    var unsupportedMessage: String { L("这个市场暂时没有按日的券商评级调整数据") }
    var loadingTitle: String { self == .grade ? L("正在加载「%@」评级升降…") : L("正在加载「%@」分析师评级…") }
    var loadingHint: String {
        self == .grade ? L("评级是每日跑批的结果，稍候即可看到升降") : L("首次加载要逐只汇总券商评级，可能需要一两分钟")
    }
    var infoLines: [String] {
        if self == .grade {
            return [
                L("范围：当前所选指数的成分股。每只股票每天有一个综合等级（A+ 到 F 共 13 档），和上一个评级日相比变了几档，就是一条升降。"),
                L("环：变动之后的新等级。最里圈 A 段（A+ / A / A-），中间圈 B 段，最外圈 C 及以下。"),
                L("颜色：红 = 升档，绿 = 降档；颜色越深、气泡越大，变的档数越多。气泡最后一行是「▲ / ▼ 变档数」。"),
                L("数量：只画当天变档最多的前 10 只，其余点「另有 N 个 · 查看全部」。"),
                L("评级升降只是事实陈列，不代表后续涨跌，不构成投资建议。")
            ]
        }
        return [
            L("范围：当前所选指数的成分股。一只股票当天被几家券商上调评级、几家下调评级，相减得到净值，净值不为 0 才画。"),
            L("环：被调整后的新评级归类。最里圈买入类（买入 / 增持 / 跑赢大盘等），中间圈中性类，最外圈卖出类。"),
            L("颜色：红 = 净上调，绿 = 净下调；颜色越深、气泡越大，净调整的家数越多。气泡最后一行是「▲ / ▼ 净家数」。"),
            L("数量：只画当天净调整最多的前 10 只，其余点「另有 N 个 · 查看全部」。只统计美股，维持评级不算。"),
            L("券商评级调整只是事实陈列，不代表后续涨跌，不构成投资建议。")
        ]
    }
}

@MainActor
final class GradeEventsViewModel: ObservableObject {
    let kind: RadarEventKind
    init(kind: RadarEventKind = .grade) { self.kind = kind }

    @Published private(set) var response: GradeEventsResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var failed = false
    @Published var selectedIndex = 0
    /// 顶部行业胶囊的筛选（nil = 全部行业）：与缠论雷达共用同一个行业键，只留该行业的评级升降。
    @Published var sectorFilter: String?

    /// 已加载数据对应的 (市场, 指数)，以及当前请求的 (市场, 指数)：两者不同 = 刚切了市场 / 指数、旧数据不能再展示。
    @Published private(set) var loadedKey = ""
    @Published private(set) var requestedKey = ""
    /// 最近一次失败的范围；视图按「当前范围」判断，切到别的范围时旧失败不再算数。
    @Published private(set) var failedKey = ""

    /// 气泡最多画几只（变档最多的在前），其余点「另有 N 个 · 查看全部」。
    static let bubbleLimit = 10
    /// 13 档字母等级，A+ 最高、F 最低（与后端 GRADE_ORDER 一致）。
    static let gradeOrder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]

    /// 只有响应与当前所选 (市场, 指数) 一致才展示；切市场 / 指数后旧数据不再显示（与缠论雷达同一规则）。
    var days: [GradeDay] { response != nil && loadedKey == requestedKey ? (response?.days ?? []) : [] }

    /// 整页「正在加载」：当前所选范围还没有可展示的数据（首次进入、切市场 / 指数）。
    var isScanning: Bool { isLoading && days.isEmpty }

    /// 同一范围重新加载（如强制刷新）：旧气泡调暗、暂不响应点按。
    var isReloading: Bool { isLoading && !days.isEmpty }

    var selectedDay: GradeDay? {
        guard !days.isEmpty else { return nil }
        return days[min(max(selectedIndex, 0), days.count - 1)]
    }

    /// 读取失败（接口报错，或后端说评级数据读取失败）。
    var hasError: Bool { failed || response?.available == false }

    /// 分析师评级：当前范围的市场没有按日券商评级数据（A 股 / 港股）。
    var isUnsupported: Bool { response?.supported == false && loadedKey == requestedKey }

    /// 分析师评级：后台还在逐只拉券商评级的股票只数（>0 时事件可能不全）。
    var pendingSymbols: Int { loadedKey == requestedKey ? (response?.pendingSymbols ?? 0) : 0 }

    /// 视图当前所选范围的键（与 load 里的 key 同格式）。
    static func scopeKey(market: String, universe: String?) -> String { "\(market)|\(universe ?? "")" }

    /// 视图当前所选范围还没有可展示的数据：切市场 / 指数的那一帧就为 true（不等 .task 起来、不依赖 isLoading），
    /// 与缠论雷达「选了就立刻转圈」一致。已失败的范围不算（走出错态）。
    func needsLoading(scope: String) -> Bool { loadedKey != scope && failedKey != scope }

    // MARK: - 映射成缠论雷达的数据形状

    /// 选中那一天的全部评级升降（后端已按变档数从多到少、同档数按代码排）。
    var dayEvents: [GradeEvent] {
        let all = selectedDay?.events ?? []
        guard let key = sectorFilter else { return all }
        return all.filter { ($0.sector ?? RadarDay.otherSectorKey) == key }
    }

    /// 选中日各行业的升 / 降只数（不受行业筛选影响；key 同缠论雷达，buy = 升档、sell = 降档），给行业弹层用。
    var sectorCounts: [String: [String: Int]] {
        var out: [String: [String: Int]] = [:]
        for e in selectedDay?.events ?? [] {
            let key = e.sector ?? RadarDay.otherSectorKey
            out[key, default: [:]][e.isUp ? "buy" : "sell", default: 0] += 1
        }
        return out
    }

    /// 超过 bubbleLimit 被折叠的只数。
    var hiddenCount: Int { max(0, dayEvents.count - Self.bubbleLimit) }

    /// 交给雷达画布的「一天」：前 bubbleLimit 只。
    var radarDay: RadarDay? {
        guard let day = selectedDay else { return nil }
        let all = dayEvents
        return RadarDay(date: day.date, quantFilter: nil,
                        buyCount: all.filter(\.isUp).count, sellCount: all.filter { !$0.isUp }.count,
                        signals: all.prefix(Self.bubbleLimit).map { signal(from: $0) },
                        candidates: [], sectorCounts: nil)
    }

    /// 环（由内向外）：新等级 A 段 = 0、B 段 = 1、其余（C 及以下）= 2。借缠论画布的 ageDays 分圈：
    /// 0 → 最里圈、1~3 → 中圈、其余 → 最外圈（见 SignalRadarView.bandIndex）。
    /// 一条事件所在的环：基本面 = 新等级段；分析师 = 新评级归类（买入 0 / 中性 1 / 卖出 2）。
    func ringBand(of e: GradeEvent) -> Int {
        switch kind {
        case .grade: return Self.ringBand(grade: e.toGrade)
        case .analyst: return e.toBucket == "buy" ? 0 : (e.toBucket == "sell" ? 2 : 1)
        }
    }

    static func ringBand(grade: String) -> Int {
        let idx = gradeOrder.firstIndex(of: grade) ?? (gradeOrder.count - 1)
        return idx <= 2 ? 0 : (idx <= 5 ? 1 : 2)
    }

    /// 气泡大小档（1/2/3，对应缠论一/二/三类的 58/72/86）：变 1 档最小、2 档中、3 档及以上最大。
    static func sizeTier(steps: Int) -> Int { min(max(steps, 1), 3) }

    func signal(from e: GradeEvent) -> RadarSignal {
        let side = e.isUp ? "buy" : "sell"
        return RadarSignal(
            symbol: e.symbol, name: e.name, side: side,
            label: e.isUp ? kind.upWord : kind.downWord,
            signalType: side + String(Self.sizeTier(steps: e.steps)), date: e.date, price: 0,
            strength: 0.5, bias: "neutral",
            // 颜色深浅：变 1 档最浅、2~3 档中、4 档及以上最深
            signalStrength: e.steps >= 4 ? "strong" : (e.steps >= 2 ? "medium" : "weak"),
            confirmed: true, pivotStageDepth: 0.5, subLevelVerdict: nil, subLevelLabel: nil,
            // 气泡最后一行（缠论气泡里放评级的那一行）写「▲2 / ▼1」变档数
            quantGrade: (e.isUp ? "▲" : "▼") + String(e.steps), quantScore: nil,
            quantAsOf: nil, quantStatus: nil,
            // 分圈：环 = 新等级（ringBand 0/1/2 → ageDays 0/1/4）
            ageDays: [0, 1, 4][ringBand(of: e)], sector: e.sector)
    }

    // MARK: - 拉取

    func load(market: String, universe: String?, force: Bool = false) async {
        let key = Self.scopeKey(market: market, universe: universe)
        requestedKey = key
        if !force, key == loadedKey, response != nil { return }
        isLoading = true
        failed = false
        if failedKey == key { failedKey = "" }
        defer { if requestedKey == key { isLoading = false } }
        do {
            let resp = kind == .grade
                ? try await SignalRadarService.gradeEvents(market: market, universe: universe)
                : try await SignalRadarService.analystEvents(market: market, universe: universe)
            // 加载期间用户又切了市场 / 指数：丢弃这次结果，别覆盖新请求
            guard requestedKey == key else { return }
            loadedKey = key
            response = resp
            selectedIndex = 0
        } catch {
            if Task.isCancelled || requestedKey != key { return }
            failed = true
            failedKey = key
        }
    }

    /// 后台还在补数据（pendingSymbols > 0）时每 20 秒静默重拉一次：不置 isLoading（不转圈、不调暗），
    /// 补上的事件直接出现；范围变了 / 任务取消即退出。
    func pollWhilePending(market: String, universe: String?) async {
        let key = Self.scopeKey(market: market, universe: universe)
        while !Task.isCancelled, requestedKey == key, pendingSymbols > 0 {
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            guard !Task.isCancelled, requestedKey == key else { return }
            guard let resp = try? await SignalRadarService.analystEvents(market: market, universe: universe),
                  requestedKey == key else { continue }
            response = resp
        }
    }
}
