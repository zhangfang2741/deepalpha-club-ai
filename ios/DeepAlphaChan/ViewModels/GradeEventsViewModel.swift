import Foundation

/// 雷达「基本面研究」tab 的数据：当前（市场, 指数）最近几天综合等级升降事件。
@MainActor
final class GradeEventsViewModel: ObservableObject {
    @Published private(set) var response: GradeEventsResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var failed = false
    @Published var selectedIndex = 0

    private var loadedKey = ""

    var days: [GradeDay] { response?.days ?? [] }

    var selectedDay: GradeDay? {
        guard !days.isEmpty else { return nil }
        return days[min(max(selectedIndex, 0), days.count - 1)]
    }

    /// 读取失败（接口报错，或后端说评级数据读取失败）。
    var hasError: Bool { failed || response?.available == false }

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
