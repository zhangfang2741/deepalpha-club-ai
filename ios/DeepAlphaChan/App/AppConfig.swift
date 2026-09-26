import Foundation

/// 全局配置：后端地址等。
///
/// 默认直连生产环境（Railway）。
/// 本地联调时把 `baseURL` 改为 `http://localhost:8000`，
/// 并在 Info.plist 里为 localhost 放开 ATS（工程已配置）。
enum AppConfig {
    /// 后端 API 根地址（不含 `/api/v1` 前缀）。
    // 用自定义域名而不是 Railway 的 web-production-*.up.railway.app：
    // 那个域名是平台分配的，重建服务就会变，一变线上 App 直接全挂。
    static let baseURL = URL(string: "https://api.deepalpha.club")!

    /// 所有业务接口的公共前缀。
    static let apiPrefix = "/api/v1"

    /// 网络请求超时（秒）。缠论分析含拉行情，放宽一些。
    static let requestTimeout: TimeInterval = 45

    // MARK: - 订阅
    //
    // 两档月度订阅，逐级递进：
    //   基础版 —— 解锁全量缠论分析（不受每日次数限制）+ 30 分钟次级别确认，¥38/月。
    //   高级版 —— 在基础版基础上，额外解锁信号雷达、自选批量状态计算，¥188/月。
    // 具体定价与免费试用时长在 App Store Connect / Configuration.storekit 配置，
    // 不写死在代码里（见 StoreManager.trialPeriodText，读商品实际配置生成文案）。

    /// 基础版月度订阅商品 ID（沿用历史商品 ID，避免破坏线上已订阅用户；商品 ID 里的
    /// "pro" 是历史命名，与当前展示名「基础版」无关，不必为了改名同步改 ID）。
    static let experienceMonthlyProductID = "club.deepalpha.chan.pro.monthly"

    /// 高级版月度订阅商品 ID（需与 App Store Connect / Configuration.storekit 一致）。
    static let premiumMonthlyProductID = "club.deepalpha.chan.premium.monthly"

    /// 两档订阅的原价（¥/月），付费墙用来对比展示「限时活动价」的号召力。
    /// StoreKit 商品本身没有「原价」概念——`product.displayPrice` 只反映当前实际
    /// 扣款价格（即活动价 ¥38 / ¥188，见 Configuration.storekit），这两个只是营销
    /// 对比文案用的常量，不参与任何计费逻辑，改活动策略时改这里即可。
    static let experienceOriginalPriceText = "¥88"
    static let premiumOriginalPriceText = "¥388"

    /// 免费用户每日可用的缠论分析次数（超出需订阅基础版或高级版）。
    static let freeDailyQuota = 3

    // MARK: - 分享

    /// 分享图二维码指向的下载中转页。
    ///
    /// 刻意不直接写 App Store 商品页链接：那个链接依赖 App Store ID，而二维码一旦
    /// 印进用户分享出去的图里就再也改不了。中转页由自家网站控制，iOS 访问自动跳
    /// App Store，上架前后都能用，换链接只需改网页、不用发新版本。
    static let downloadPageURL = "https://deepalpha.club/app"
}
