import Foundation

/// 雷达「基本面研究」tab 的数据：当前（市场, 指数）最近几天综合等级升降事件。
/// 画布与缠论雷达共用同一套（多环 / 浮动动画 / 摆位），这里把「选中日在场的评级升降」映射成 RadarDay + RadarSignal：
/// 升档 = 买色（红）、降档 = 卖色（绿），颜色深浅随变档数，气泡大小随新等级，环 = 距选中日的交易日数。
@MainActor
final class GradeEventsViewModel: ObservableObject {
    @Published private(set) var response: GradeEventsResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var failed = false
    @Published var selectedIndex = 0

    private var loadedKey = ""

    /// 评级升降「在场」多久：与缠论买卖点同样 5 个交易日（选中日往前数）。
    static let windowTradingDays = 5
    /// 气泡最多画几只（变档最多的在前），其余点「另有 N 个 · 查看全部」。
    static let bubbleLimit = 10
    /// 13 档字母等级，A+ 最高、F 最低（与后端 GRADE_ORDER 一致）。
    static let gradeOrder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]

    var days: [GradeDay] { response?.days ?? [] }

    var selectedDay: GradeDay? {
        guard !days.isEmpty else { return nil }
        return days[min(max(selectedIndex, 0), days.count - 1)]
    }

    /// 读取失败（接口报错，或后端说评级数据读取失败）。
    var hasError: Bool { failed || response?.available == false }

    // MARK: - 映射成缠论雷达的数据形状

    /// 选中日在场的全部升降（含更早几天仍在窗口内的），按变档数从多到少、同档数先新后旧、再按代码。
    var windowEvents: [(event: GradeEvent, age: Int)] {
        guard let day = selectedDay else { return [] }
        return days.flatMap(\.events)
            .compactMap { e -> (event: GradeEvent, age: Int)? in
                let age = Self.tradingAge(from: e.date, to: day.date)
                return age >= 0 && age < Self.windowTradingDays ? (e, age) : nil
            }
            .sorted { a, b in
                if a.event.steps != b.event.steps { return a.event.steps > b.event.steps }
                if a.age != b.age { return a.age < b.age }
                return a.event.symbol < b.event.symbol
            }
    }

    /// 超过 bubbleLimit 被折叠的只数。
    var hiddenCount: Int { max(0, windowEvents.count - Self.bubbleLimit) }

    /// 交给雷达画布的「一天」：前 bubbleLimit 只。
    var radarDay: RadarDay? {
        guard let day = selectedDay else { return nil }
        let all = windowEvents
        let signals = all.prefix(Self.bubbleLimit).map { Self.signal(from: $0.event, age: $0.age) }
        return RadarDay(date: day.date, quantFilter: nil,
                        buyCount: all.filter { $0.event.isUp }.count,
                        sellCount: all.filter { !$0.event.isUp }.count,
                        signals: Array(signals), candidates: [], sectorCounts: nil)
    }

    /// 新等级 → 气泡大小档（1/2/3，对应缠论一/二/三类的 58/72/86）：A 段最大、B 段中、其余最小。
    static func sizeTier(grade: String) -> Int {
        let idx = gradeOrder.firstIndex(of: grade) ?? (gradeOrder.count - 1)
        return idx <= 2 ? 3 : (idx <= 5 ? 2 : 1)
    }

    static func signal(from e: GradeEvent, age: Int) -> RadarSignal {
        let side = e.isUp ? "buy" : "sell"
        return RadarSignal(
            symbol: e.symbol, name: e.name, side: side,
            label: e.isUp ? L("升档") : L("降档"),
            signalType: side + String(sizeTier(grade: e.toGrade)), date: e.date, price: 0,
            strength: 0.5, bias: "neutral",
            // 颜色深浅：变 1 档最浅、2~3 档中、4 档及以上最深
            signalStrength: e.steps >= 4 ? "strong" : (e.steps >= 2 ? "medium" : "weak"),
            confirmed: true, pivotStageDepth: 0.5, subLevelVerdict: nil, subLevelLabel: nil,
            // 气泡最后一行（缠论气泡里放评级的那一行）写「▲2 / ▼1」变档数
            quantGrade: (e.isUp ? "▲" : "▼") + String(e.steps), quantScore: nil, quantAsOf: nil, quantStatus: nil, ageDays: age, sector: e.sector)
    }

    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        return f
    }()

    /// 事件日到选中日隔了几个交易日（周末不算；节假日按工作日处理，窗口是近似的）。
    static func tradingAge(from event: String, to day: String) -> Int {
        guard let a = parser.date(from: event), let b = parser.date(from: day), a <= b else { return -1 }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(secondsFromGMT: 0)!
        var age = 0
        var d = a
        while d < b {
            d = cal.date(byAdding: .day, value: 1, to: d)!
            if cal.component(.weekday, from: d) != 1 && cal.component(.weekday, from: d) != 7 { age += 1 }
        }
        return age
    }

    // MARK: - 拉取

    func load(market: String, universe: String?, force: Bool = false) async {
        let key = "\(market)|\(universe ?? "")"
        if !force, key == loadedKey, response != nil { return }
        isLoading = true
        failed = false
        defer { isLoading = false }
        do {
            let resp = try await SignalRadarService.gradeEvents(market: market, universe: universe)
            loadedKey = key
            response = resp
            selectedIndex = 0
        } catch {
            if Task.isCancelled { return }
            failed = true
        }
    }
}
