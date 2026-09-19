import StoreKit

/// SKAdNetwork 转化值上报：把「安装后关键行为」编码成个位数分档，供 Google Ads
/// App Campaign 在 iOS 无 IDFA 场景下评估广告效果、决定要不要继续加预算。
///
/// 只选三个粗粒度阶段，不逐个行为上报：Apple 出于隐私考虑只给 0-63 共 64 档，
/// 而且同一批安装量不够大时系统会把 fine value 直接抹掉只保留 coarse value，
/// 分得越细越容易被抹掉，粗才稳。
enum SKAdNetworkAttribution {
    enum Event: Int {
        /// 完成注册/登录：证明是真实用户，不是安装了就删的僵尸量。
        case registered = 1
        /// 至少完整跑过一次缠论分析：证明有实际使用，不只是打开看了一眼。
        case usedAnalysis = 2
        /// 订阅了 Pro：证明这个渠道来的用户能变现，是 Google Ads 优化最看重的信号。
        case subscribed = 3

        /// 精细值不一定能传到 Google 手上，独立给一档粗分类兜底。
        var coarseValue: SKAdNetwork.CoarseConversionValue {
            switch self {
            case .registered: return .low
            case .usedAnalysis: return .medium
            case .subscribed: return .high
            }
        }
    }

    /// 上报一次转化事件。
    ///
    /// 只在事件真实发生时调用，值故意设计成单调递增（1→2→3），因为 postback 只在
    /// 归因窗口关闭时发一次、只反映"当时最新的值"，不是每次调用都单独送一条——
    /// 调小了会覆盖掉之前更有价值的信号。`subscribed` 命中后直接锁窗口提前发送，
    /// 这是全链路里最关键的信号，没必要等窗口自然到期才让 Google 看到。
    static func report(_ event: Event) {
        SKAdNetwork.updatePostbackConversionValue(
            event.rawValue,
            coarseValue: event.coarseValue,
            lockWindow: event == .subscribed
        ) { error in
            if let error {
                print("[SKAdNetworkAttribution] 上报失败: \(error.localizedDescription)")
            }
        }
    }
}
