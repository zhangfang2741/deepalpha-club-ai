import Foundation

/// 雷达「基本面研究」tab 的数据：当前（市场, 指数）最近几天综合等级升降事件。
/// 画布与缠论雷达共用同一套（多环 / 浮动动画 / 摆位），这里把「选中日的评级升降」映射成 RadarDay + RadarSignal：
/// 升档 = 买色（红）、降档 = 卖色（绿），颜色深浅与气泡大小随变档数，环 = 新等级（A / B / C 及以下）。
@MainActor
final class GradeEventsViewModel: ObservableObject {
    @Published private(set) var response: GradeEventsResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var failed = false
    @Published var selectedIndex = 0
    /// 顶部行业胶囊的筛选（nil = 全部行业）：与缠论雷达共用同一个行业键，只留该行业的评级升降。
    @Published var sectorFilter: String?

    /// 已加载数据对应的 (市场, 指数)，以及当前请求的 (市场, 指数)：两者不同 = 刚切了市场 / 指数、旧数据不能再展示。
    private var loadedKey = ""
    private var requestedKey = ""

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
                        signals: all.prefix(Self.bubbleLimit).map { Self.signal(from: $0) },
                        candidates: [], sectorCounts: nil)
    }

    /// 环（由内向外）：新等级 A 段 = 0、B 段 = 1、其余（C 及以下）= 2。借缠论画布的 ageDays 分圈：
    /// 0 → 最里圈、1~3 → 中圈、其余 → 最外圈（见 SignalRadarView.bandIndex）。
    static func ringBand(grade: String) -> Int {
        let idx = gradeOrder.firstIndex(of: grade) ?? (gradeOrder.count - 1)
        return idx <= 2 ? 0 : (idx <= 5 ? 1 : 2)
    }

    /// 气泡大小档（1/2/3，对应缠论一/二/三类的 58/72/86）：变 1 档最小、2 档中、3 档及以上最大。
    static func sizeTier(steps: Int) -> Int { min(max(steps, 1), 3) }

    static func signal(from e: GradeEvent) -> RadarSignal {
        let side = e.isUp ? "buy" : "sell"
        return RadarSignal(
            symbol: e.symbol, name: e.name, side: side,
            label: e.isUp ? L("升档") : L("降档"),
            signalType: side + String(sizeTier(steps: e.steps)), date: e.date, price: 0,
            strength: 0.5, bias: "neutral",
            // 颜色深浅：变 1 档最浅、2~3 档中、4 档及以上最深
            signalStrength: e.steps >= 4 ? "strong" : (e.steps >= 2 ? "medium" : "weak"),
            confirmed: true, pivotStageDepth: 0.5, subLevelVerdict: nil, subLevelLabel: nil,
            // 气泡最后一行（缠论气泡里放评级的那一行）写「▲2 / ▼1」变档数
            quantGrade: (e.isUp ? "▲" : "▼") + String(e.steps), quantScore: nil,
            quantAsOf: nil, quantStatus: nil,
            // 分圈：环 = 新等级（ringBand 0/1/2 → ageDays 0/1/4）
            ageDays: [0, 1, 4][ringBand(grade: e.toGrade)], sector: e.sector)
    }

    // MARK: - 拉取

    func load(market: String, universe: String?, force: Bool = false) async {
        let key = "\(market)|\(universe ?? "")"
        requestedKey = key
        if !force, key == loadedKey, response != nil { return }
        isLoading = true
        failed = false
        defer { if requestedKey == key { isLoading = false } }
        do {
            let resp = try await SignalRadarService.gradeEvents(market: market, universe: universe)
            // 加载期间用户又切了市场 / 指数：丢弃这次结果，别覆盖新请求
            guard requestedKey == key else { return }
            loadedKey = key
            response = resp
            selectedIndex = 0
        } catch {
            if Task.isCancelled || requestedKey != key { return }
            failed = true
        }
    }
}
