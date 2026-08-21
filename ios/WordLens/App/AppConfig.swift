// App/AppConfig.swift
import Foundation

/// 全局配置：后端地址等。
enum AppConfig {
    /// 生产环境（Railway，与 DeepAlphaChan 共用同一个后端服务）。
    ///
    /// 必须用自有域名，不能用 Railway 分配的 `*.up.railway.app`：后者是平台临时
    /// 域名，重建服务时会变，而 App Store 上的二进制改不了硬编码 URL——域名一变
    /// 线上所有用户直接全挂，只能重新提交审核等一两天。自有域名走 Cloudflare，
    /// 后端换平台也只需改一条 DNS 记录。
    static let baseURL = URL(string: "https://api.deepalpha.club")!
    static let apiPrefix = "/api/v1/vocabulary"

    /// App 显示名。锁屏「正在播放」等处需要用到，从 Info.plist 读而不是硬编码，
    /// 避免改名时漏掉某处（上次「鹦鹉学舌」→「鹦鹉背单词」就在这里留了个残留）。
    static let displayName: String =
        Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? L("鹦鹉背单词")

    /// 隐私政策 / 服务条款。App Store Connect 必填隐私政策 URL，审核员也会
    /// 检查 App 内可达（设置页「关于」分组）。
    static let privacyPolicyURL = URL(string: "https://deepalpha.club/wordlens/privacy")!
    static let termsOfServiceURL = URL(string: "https://deepalpha.club/wordlens/terms")!

    // MARK: - 订阅与免费额度

    /// 月度订阅商品 ID（需与 App Store Connect / Products.storekit 一致）。
    /// 价格在 App Store Connect 里设为约 ¥29/月的价格档，其它地区由 Apple 按档位
    /// 自动换算，端上只读 `product.displayPrice` 展示本地化价格，不硬编码金额。
    static let proMonthlyProductID = "club.deepalpha.wordlens.pro.monthly"

    /// 免费用户每日可拍照识别的张数（超出需订阅）。
    static let freeDailyPhotoLimit = 3

    /// 免费用户每日可学习的新单词数（超出需订阅）。
    /// 「学习」= 在学习页把一个单词完整播放一遍；当天已学过的词可无限次重复，
    /// 只有当天学第 N+1 个「新」词时才受限。
    static let freeDailyWordLimit = 20

    static let requestTimeout: TimeInterval = 30
    /// 拍照识别调 LLM，比普通请求慢很多，单独给更长超时。
    ///
    /// 90s 是经验值：必须 < Cloudflare 的边缘 idle timeout（实测 100s 左右），
    /// 否则 URLSession 会被 CFNetwork 在 socket idle 阶段直接 -1005 reset
    /// （kCFStreamErrorCodeKey=54）。90s 让 NSURLSession 主动触发超时重试，
    /// 而不是被底层掐断。
    static let recognizeTimeout: TimeInterval = 90
    /// 整体资源（上传 + 服务器处理 + 接收响应）总耗时上限。
    static let resourceTimeout: TimeInterval = 180
}
