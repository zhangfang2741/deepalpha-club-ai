import Foundation

/// 信号雷达使用前的风险确认状态（端上，UserDefaults 持久化）。
///
/// 雷达把多只标的的买卖点集中展示成一图，比单只标的的分析详情页更容易被当成
/// 「抄作业」的操作清单——单靠 AnalysisTabView 里那行常驻风险提示不够，这里需要
/// 用户主动勾选确认过才放行，降低「用户只看雷达买卖点做交易导致亏损」的误解
/// 与由此带来的责任风险。
///
/// 只在「已订阅高级版」的用户第一次进入雷达时出现一次；确认过不再重复弹，
/// 除非声明文案发生实质性变化（见 currentVersion）。
@MainActor
final class RadarConsent: ObservableObject {
    /// 声明文案版本号：以后改了声明的实质内容（新增风险点、改变责任表述等，
    /// 不是纯措辞微调）就把这个数字加一，旧版本的确认记录自动失效、强制重新确认。
    static let currentVersion = 1

    @Published private(set) var hasAgreed: Bool

    private let defaults = UserDefaults.standard
    private let versionKey = "radar_disclaimer_agreed_version"

    init() {
        hasAgreed = defaults.integer(forKey: versionKey) >= Self.currentVersion
    }

    func agree() {
        defaults.set(Self.currentVersion, forKey: versionKey)
        hasAgreed = true
    }
}
