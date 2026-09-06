import Foundation
import SwiftData

/// 用户自己的生辰记录（单条，MVP 不支持家人档案）。
/// chartResponseJSON 存最近一次 /chart 的完整响应（JSON blob），避免把 Pillar/DaYunStep
/// 这类嵌套 Codable 结构逐字段拆成 SwiftData 关系模型——排盘结果整体只读展示，不需要按字段查询。
@Model
public final class BirthProfile {
    @Attribute(.unique) public var id: String
    public var birthDate: String
    public var birthTime: String?
    public var birthCity: String
    public var gender: String
    public var chartResponseJSON: Data

    public init(id: String = "me", birthDate: String, birthTime: String?, birthCity: String,
                gender: String, chartResponseJSON: Data) {
        self.id = id
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
        self.chartResponseJSON = chartResponseJSON
    }
}
