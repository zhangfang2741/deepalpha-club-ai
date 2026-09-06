import Foundation
import SwiftData

/// BirthProfile 是 SwiftData @Model（引用类型，非 Sendable），不能原样跨 actor 边界返回给
/// 调用方（Swift 6 严格并发下会报错）。读取时在 actor 内部把字段拆成这个 Sendable 快照。
public struct BirthProfileSnapshot: Sendable, Equatable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String
    public let chart: BaziChartResponse
}

/// 本地存储读写 actor（@ModelActor 生成 executor 隔离）。
/// 管两张表：用户自己的生辰档案(单条) + 今日运势缓存(按日期去重)。
@ModelActor
public actor BaziLocalStore {
    private static let profileId = "me"

    /// 保存/覆盖生辰档案 + 最近一次排盘结果。
    public func saveProfile(birthDate: String, birthTime: String?, birthCity: String,
                            gender: String, chart: BaziChartResponse) throws {
        let context = modelContext
        let chartJSON = try JSONEncoder().encode(chart)
        let targetId = Self.profileId
        let existing = try context.fetch(FetchDescriptor<BirthProfile>(
            predicate: #Predicate { $0.id == targetId }))
        if let row = existing.first {
            row.birthDate = birthDate
            row.birthTime = birthTime
            row.birthCity = birthCity
            row.gender = gender
            row.chartResponseJSON = chartJSON
        } else {
            context.insert(BirthProfile(
                id: Self.profileId, birthDate: birthDate, birthTime: birthTime,
                birthCity: birthCity, gender: gender, chartResponseJSON: chartJSON))
        }
        try context.save()
    }

    /// 读取本地生辰档案；没有则返回 nil（新用户态）。
    /// 返回 Sendable 快照而不是 BirthProfile 本身——@Model 是引用类型，不能跨 actor 边界传递。
    public func loadProfile() throws -> BirthProfileSnapshot? {
        let targetId = Self.profileId
        guard let row = try modelContext.fetch(FetchDescriptor<BirthProfile>(
            predicate: #Predicate { $0.id == targetId })).first else {
            return nil
        }
        let chart = try JSONDecoder().decode(BaziChartResponse.self, from: row.chartResponseJSON)
        return BirthProfileSnapshot(
            birthDate: row.birthDate, birthTime: row.birthTime,
            birthCity: row.birthCity, gender: row.gender, chart: chart)
    }

    /// 写入某天的今日运势文本（同日期覆盖）。
    public func saveTodayFortune(dateKey: String, text: String) throws {
        let context = modelContext
        let existing = try context.fetch(FetchDescriptor<DailyFortuneCache>(
            predicate: #Predicate { $0.dateKey == dateKey }))
        if let row = existing.first {
            row.text = text
        } else {
            context.insert(DailyFortuneCache(dateKey: dateKey, text: text))
        }
        try context.save()
    }

    /// 读取某天的今日运势缓存；没有(还没拉过/换了一天)返回 nil。
    public func loadFortune(dateKey: String) throws -> String? {
        try modelContext.fetch(FetchDescriptor<DailyFortuneCache>(
            predicate: #Predicate { $0.dateKey == dateKey })).first?.text
    }
}

/// 默认磁盘容器的工厂：失败(磁盘满/迁移冲突)返回 nil，App 降级为不持久化(每次都重新走网络)。
public enum BaziLocalStoreDefault {
    public static func make() -> BaziLocalStore? {
        guard let container = try? ModelContainer(for: BirthProfile.self, DailyFortuneCache.self) else {
            return nil
        }
        return BaziLocalStore(modelContainer: container)
    }
}
