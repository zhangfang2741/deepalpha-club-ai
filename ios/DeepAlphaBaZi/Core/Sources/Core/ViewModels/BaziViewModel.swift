import Foundation
import Observation

/// 八字主流程状态机：本地档案(有/无) → 提交生辰生成排盘 → 加载今日运势(本地缓存优先)。
@MainActor @Observable
public final class BaziViewModel {
    public private(set) var profile: BirthProfileSnapshot?
    public private(set) var dailyFortuneText: String?
    public private(set) var isSubmittingBirthInfo = false
    public private(set) var isLoadingFortune = false
    public var formError: String?
    public var fortuneError: String?

    let service: any BaziServicing
    let store: BaziLocalStore?
    /// 今天的日期 key（"yyyy-MM-dd"），测试注入固定值，生产环境默认取当前时间。
    let todayKeyProvider: @Sendable () -> String

    public init(service: any BaziServicing, store: BaziLocalStore?,
                todayKeyProvider: @escaping @Sendable () -> String = { BaziViewModel.formatDateKey(Date()) }) {
        self.service = service
        self.store = store
        self.todayKeyProvider = todayKeyProvider
    }

    public nonisolated static func formatDateKey(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    /// App 启动 / 首页出现时调用：有本地档案直接进已排盘态，没有则停在填表态。
    public func loadLocalProfile() async {
        guard let store else { return }
        profile = try? await store.loadProfile()
    }

    /// 提交生辰表单：调 /chart，成功后落本地并进入已排盘态。
    /// 提交中再次调用直接忽略——避免双击/视图重建导致并发重复请求。
    public func submitBirthInfo(birthDate: String, birthTime: String?,
                                birthCity: String, gender: String) async {
        guard !isSubmittingBirthInfo else { return }
        formError = nil
        isSubmittingBirthInfo = true
        defer { isSubmittingBirthInfo = false }
        do {
            let chart = try await service.getChart(BaziChartRequest(
                birthDate: birthDate, birthTime: birthTime, birthCity: birthCity, gender: gender))
            if let store {
                try? await store.saveProfile(
                    birthDate: birthDate, birthTime: birthTime, birthCity: birthCity,
                    gender: gender, chart: chart)
            }
            profile = BirthProfileSnapshot(
                birthDate: birthDate, birthTime: birthTime, birthCity: birthCity,
                gender: gender, chart: chart)
        } catch let e as APIError {
            formError = e.message
        } catch {
            formError = "排盘失败：\(error.localizedDescription)"
        }
    }

    /// 今日运势：本地缓存命中直接展示；未命中才调用 AI 接口(避免同一天内重复付费调用)。
    /// 加载中再次调用直接忽略——避免视图重复触发 .task 时并发打两次付费接口。
    public func loadDailyFortuneIfNeeded() async {
        guard !isLoadingFortune else { return }
        guard let profile else { return }
        // 无条件清空，不能只在缓存未命中分支清——否则缓存命中时上一次的旧错误会和
        // 新展示的运势文本同屏出现（同时显示"加载失败"和一段有效的运势内容）。
        fortuneError = nil
        let dateKey = todayKeyProvider()
        if let store, let cached = try? await store.loadFortune(dateKey: dateKey) {
            dailyFortuneText = cached
            return
        }
        isLoadingFortune = true
        defer { isLoadingFortune = false }
        do {
            let response = try await service.getInterpretation(InterpretationRequest(
                birthDate: profile.birthDate, birthTime: profile.birthTime,
                birthCity: profile.birthCity, gender: profile.gender, section: .daily))
            dailyFortuneText = response.text
            if let store {
                try? await store.saveTodayFortune(dateKey: dateKey, text: response.text)
            }
        } catch let e as APIError {
            fortuneError = e.message
        } catch {
            fortuneError = "今日运势加载失败：\(error.localizedDescription)"
        }
    }
}
