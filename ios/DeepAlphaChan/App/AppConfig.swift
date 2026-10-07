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
    // 只有一个会员：月度订阅 ¥128/月，解锁全部权益（不限次缠论分析、30 分钟次级别 / 周线看日线、
    // 每日雷达与历史回看、自选不限数量与全部结构状态）。以前分基础版（¥88）和高级版，2026-10-05 合并。
    // 具体定价在 App Store Connect / Configuration.storekit 配置，不写死在代码里
    // （见 StoreManager.trialPeriodText，读商品实际配置生成文案）。

    /// 会员月度订阅商品 ID（需与 App Store Connect / Configuration.storekit 一致）。
    /// 沿用 1.0 起就在线上卖的 `pro.monthly`（ASC 里唯一已过审的订阅商品），价格 / 入门优惠只在 ASC 改。
    /// 1.2 开发期间曾计划改卖 `premium.monthly`，但它从未在 ASC 创建过——不要再改回去，
    /// 否则付费墙拿不到商品，审核按 2.1 必拒（2026-10-07 发版检查发现）。
    static let membershipMonthlyProductID = "club.deepalpha.chan.pro.monthly"

    // MARK: - 示例自选

    /// 每个用户默认送的三只示例自选（美/A/港龙头；A 股选贵州茅台而非市值第一的工商银行，
    /// 银行股缠论结构不明显）。与后端 app/services/watchlist.py 的 SAMPLE_ITEMS 保持一致。
    /// 这三只：不占自选名额、点进去不扣每日免费额度、可看完整 30 分钟次级别确认。
    static let sampleSymbols: [StockMarket: String] = [.us: "NVDA", .cn: "600519", .hk: "0700"]

    /// 是否示例股。按市场比对（A 股 000700 与港股 0700 数字相同，不能只看代码）；
    /// 容忍用户输入的写法差异：大小写、.HK/.SS/.SZ 后缀、港股前导零（700 / 0700 / 00700）。
    static func isSampleSymbol(market: StockMarket, symbol: String) -> Bool {
        guard let sample = sampleSymbols[market] else { return false }
        let raw = symbol.trimmingCharacters(in: .whitespaces).uppercased()
            .split(separator: ".").first.map(String.init) ?? ""
        if market == .hk, let a = Int(raw), let b = Int(sample) { return a == b }
        return raw == sample
    }

    /// 晨报是否上线。当前隐藏（MainTabView 里注释掉了晨报 Tab）：关着时不申请推送权限（推送只用来通知晨报）。
    /// 重新挂回晨报 Tab 时改成 true。
    static let morningReportEnabled = false

    /// 免费用户每日可用的缠论分析次数（超出需订阅会员）。
    static let freeDailyQuota = 3

    // MARK: - 分享

    /// 分享图二维码指向的下载中转页。
    ///
    /// 刻意不直接写 App Store 商品页链接：那个链接依赖 App Store ID，而二维码一旦
    /// 印进用户分享出去的图里就再也改不了。中转页由自家网站控制，iOS 访问自动跳
    /// App Store，上架前后都能用，换链接只需改网页、不用发新版本。
    static let downloadPageURL = "https://deepalpha.club/app"
}
