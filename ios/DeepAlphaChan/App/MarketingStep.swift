#if DEBUG && targetEnvironment(simulator)
import Foundation

/// 与主机生成的旁白时间轴共用步骤编号。
struct MarketingStep: Decodable {
    let step_id: String
    let time_sec: Double
    let layers: [String]
}
#endif
