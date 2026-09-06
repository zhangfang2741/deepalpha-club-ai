import Foundation
import SwiftData

/// "今日运势"文本缓存，按日期（"yyyy-MM-dd"）去重，避免同一天内重复调用付费 LLM 接口。
@Model
public final class DailyFortuneCache {
    @Attribute(.unique) public var dateKey: String
    public var text: String

    public init(dateKey: String, text: String) {
        self.dateKey = dateKey
        self.text = text
    }
}
