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

    /// 月度订阅商品 ID（需与 App Store Connect / Configuration.storekit 一致）。
    static let proMonthlyProductID = "club.deepalpha.chan.pro.monthly"

    /// 免费用户每日可用的缠论分析次数（超出需订阅）。
    static let freeDailyQuota = 3

    // MARK: - 分享

    /// 分享图二维码指向的下载中转页。
    ///
    /// 刻意不直接写 App Store 商品页链接：那个链接依赖 App Store ID，而二维码一旦
    /// 印进用户分享出去的图里就再也改不了。中转页由自家网站控制，iOS 访问自动跳
    /// App Store，上架前后都能用，换链接只需改网页、不用发新版本。
    static let downloadPageURL = "https://deepalpha.club/app"
}
