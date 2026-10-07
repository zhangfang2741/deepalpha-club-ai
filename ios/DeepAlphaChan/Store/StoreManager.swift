import Foundation
import OSLog
import StoreKit

private let storeLog = Logger(subsystem: "club.deepalpha.chan", category: "store")

/// 订阅层级：免费 / 会员。
///
/// 2026-10-05 起只有一个会员（¥128/月，全部权益）。以前分基础版（¥88，解锁不限次分析）和高级版
/// （另加次级别确认 / 信号雷达 / 自选批量状态），现在合并：旧的基础版订阅者续订期内同样按会员处理（见
/// `refreshSubscriptionStatus`）。枚举保留 `premium` 这个名字，是因为全 App 的门禁和传给后端的
/// 档位字符串（`apiValue`）都叫它，改名要连带改很多处而没有收益。
enum SubscriptionTier: Int, Comparable {
    case free = 0
    case premium = 1

    static func < (lhs: SubscriptionTier, rhs: SubscriptionTier) -> Bool { lhs.rawValue < rhs.rawValue }

    /// 传给后端的档位字符串（自选上限按档位区分，见 app/services/watchlist.py 的 TIER_LIMITS；
    /// 后端仍保留 "basic" 档，只为兼容还在发 "basic" 的旧版 App，新版不再发送）。
    var apiValue: String {
        switch self {
        case .free: return "free"
        case .premium: return "premium"
        }
    }
}

/// 订阅管理：基于 StoreKit 2，端上用加密签名凭证判断订阅状态。
///
/// `Transaction.currentEntitlements` 返回的是 Apple 签名并由系统验签的 JWS，
/// 因此端上判断已具备基本防篡改能力，满足 MVP 需要（服务端校验为后续加固项）。
@MainActor
final class StoreManager: ObservableObject {
    @Published private(set) var products: [Product] = []
    /// 订阅状态。初值取上次查到的结果（见 `lastTierKey`）：StoreKit 查权益是异步的，初值一律 `.free` 时，
    /// 会员打开 App 的头几百毫秒到几秒里，雷达会先按「未订阅」摆示例日、再切成真实数据，气泡图跟着变一次。
    /// 这个缓存只用来避免界面先闪一下，真正的判断仍是 `refreshSubscriptionStatus` 查到的结果（随即覆盖）。
    @Published private(set) var tier: SubscriptionTier = StoreManager.cachedTier()
    /// 正在购买的商品 ID（nil = 没有进行中的购买）。
    @Published private(set) var purchasingProductID: String?
    var purchaseInProgress: Bool { purchasingProductID != nil }
    @Published private(set) var loadFailed = false

    private var updatesTask: Task<Void, Never>?

    private static let lastTierKey = "store.lastKnownTier"

    private static func cachedTier() -> SubscriptionTier {
        UserDefaults.standard.integer(forKey: lastTierKey) == SubscriptionTier.premium.rawValue ? .premium : .free
    }

    init() {
        updatesTask = observeTransactionUpdates()
        Task {
            await loadProducts()
            await refreshSubscriptionStatus()
        }
    }

    deinit { updatesTask?.cancel() }

    /// 是否是会员：解锁不限次缠论分析、次级别确认、信号雷达、自选批量状态计算。
    var isSubscribed: Bool { tier != .free }
    /// 同 `isSubscribed`。合并成一个会员后两者含义相同，保留这个名字是因为各处门禁都在用它。
    var isPremium: Bool { tier == .premium }

    /// 会员月度订阅商品（付费墙上卖的唯一商品）。
    var membershipProduct: Product? {
        products.first { $0.id == AppConfig.membershipMonthlyProductID }
    }

    /// 当前 Apple 账户是否还能享受推介优惠（新客价 / 免费试用）。Apple 按订阅群组判定：
    /// 群组里任一商品用过推介优惠，两档都不再有资格——正好对应「新客专享」。
    /// 默认 false：资格没查到之前不展示优惠价，宁可少展示也不能让老用户看到拿不到的价格。
    @Published private(set) var isEligibleForIntroOffer = false

    /// 该商品对当前用户可用的推介优惠；没有配置或没有资格时为 nil。
    private func introOffer(_ product: Product) -> Product.SubscriptionOffer? {
        guard isEligibleForIntroOffer else { return nil }
        return product.subscription?.introductoryOffer
    }

    /// 某个订阅商品当前是否有资格享受免费试用（用于文案：「开始 N 天免费试用」）。
    func offersFreeTrial(_ product: Product) -> Bool {
        introOffer(product)?.paymentMode == .freeTrial
    }

    /// 免费试用时长文案（如「3 天」）：直接读商品在 App Store Connect / Configuration.storekit
    /// 里的实际配置，不在代码里硬编码天数——试用时长以后只改配置就行，不用跟着改文案。
    func trialPeriodText(_ product: Product) -> String? {
        guard let offer = introOffer(product), offer.paymentMode == .freeTrial else { return nil }
        return Self.periodText(offer.period)
    }

    /// 新客专享价（推介优惠里的「按期付费 / 预付」，非免费试用）。正价就是
    /// `product.displayPrice`，两个价格都来自 App Store，不在代码里写死任何金额。
    struct IntroDiscount {
        /// 如「¥38.00/月」
        let priceText: String
        /// 如「首月」「前 3 个月」
        let durationText: String
    }

    func introDiscount(_ product: Product) -> IntroDiscount? {
        guard let offer = introOffer(product),
              offer.paymentMode == .payAsYouGo || offer.paymentMode == .payUpFront
        else { return nil }
        let isMonthly = offer.period.unit == .month && offer.period.value == 1
        let price: String
        let totalMonths: Int?
        if offer.paymentMode == .payAsYouGo {
            // 按期付费：每期付 displayPrice，共 periodCount 期
            price = isMonthly ? L("%@/月", offer.displayPrice)
                              : L("%@/%@", offer.displayPrice, Self.periodText(offer.period))
            totalMonths = offer.period.unit == .month ? offer.period.value * offer.periodCount : nil
        } else {
            // 预付：一次付清整段优惠期
            price = offer.displayPrice
            totalMonths = offer.period.unit == .month ? offer.period.value : nil
        }
        let duration: String
        if totalMonths == 1 {
            duration = L("首月")
        } else if let totalMonths {
            duration = L("前 %@", L("%lld 个月", totalMonths))
        } else {
            duration = L("前 %@", Self.periodText(offer.period))
        }
        return IntroDiscount(priceText: price, durationText: duration)
    }

    private static func periodText(_ period: Product.SubscriptionPeriod) -> String {
        switch period.unit {
        case .day: return L("%lld 天", period.value)
        case .week: return L("%lld 周", period.value)
        case .month: return L("%lld 个月", period.value)
        case .year: return L("%lld 年", period.value)
        @unknown default: return ""
        }
    }

    // MARK: - 加载与状态

    /// 商品加载失败的具体原因（付费墙上小字显示）：「暂时无法加载订阅信息」本身分不出是 App Store 没返回这个商品
    /// （商品状态 / 协议 / 地区未上架）还是网络请求出错，排查时得知道是哪一种。
    @Published private(set) var loadDiagnostic: String?

    func loadProducts() async {
        do {
            // 只加载在售的会员商品；旧的基础版商品已停售，不用加载（识别旧订阅者靠 currentEntitlements）
            let items = try await Product.products(for: [AppConfig.membershipMonthlyProductID])
            products = items
            loadFailed = items.isEmpty
            loadDiagnostic = items.isEmpty
                ? L("App Store 没有返回商品 %@（商品状态、价格或协议可能还没生效）", AppConfig.membershipMonthlyProductID)
                : nil
            // 空数组是最难查的一种失败：StoreKit 不抛错，只是什么都没返回，界面却显示
            // 「暂时无法加载订阅信息」。把已知成因写进日志，省得每次从零排查。
            if items.isEmpty {
                storeLog.error("""
                    商品列表为空（未抛错）。依次检查：\
                    ①本地调试：Scheme 是否挂了 Configuration.storekit，且该文件里所有 identifier / id / \
                    internalID 都是合法 UUID（含 DEEP 这类非十六进制字符时 Xcode 会静默忽略整个配置）；\
                    ②真机 / TestFlight：App Store Connect 的付费应用协议是否「生效中」、产品 ID 是否与 \
                    \(AppConfig.membershipMonthlyProductID, privacy: .public) 完全一致、订阅是否处于可售状态
                    """)
            }
            await refreshIntroEligibility()
        } catch {
            storeLog.error("商品加载失败: \(error.localizedDescription, privacy: .public)")
            loadFailed = true
            loadDiagnostic = L("请求 App Store 出错：%@", error.localizedDescription)
        }
    }

    /// 资格是订阅群组级的（旧基础版与会员同在一个群组），查会员商品即可。
    private func refreshIntroEligibility() async {
        guard let subscription = products.first?.subscription else {
            isEligibleForIntroOffer = false
            return
        }
        isEligibleForIntroOffer = await subscription.isEligibleForIntroOffer
    }

    /// 遍历当前有效权益判断是否是会员。旧的基础版商品（已停售）仍在有效期内的订阅者同样按会员处理——
    /// 合并成一个会员后，已付费的人不能少权益，也不用重新订阅。
    func refreshSubscriptionStatus() async {
        var highest: SubscriptionTier = .free
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result, transaction.revocationDate == nil
            else { continue }
            switch transaction.productID {
            case AppConfig.membershipMonthlyProductID, AppConfig.legacyBasicMonthlyProductID:
                highest = .premium
            default:
                continue
            }
        }
        tier = highest
        UserDefaults.standard.set(highest.rawValue, forKey: Self.lastTierKey)
        // 买过一次（含用了新客价）资格就没了，购买/续订/跨设备同步后都要重新判定
        await refreshIntroEligibility()
    }

    // MARK: - 购买与恢复

    @discardableResult
    func purchase(_ product: Product) async -> Bool {
        purchasingProductID = product.id
        defer { purchasingProductID = nil }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                guard case .verified(let transaction) = verification else { return false }
                await transaction.finish()
                await refreshSubscriptionStatus()
                if isSubscribed { SKAdNetworkAttribution.report(.subscribed) }
                return isSubscribed
            case .userCancelled, .pending:
                return false
            @unknown default:
                return false
            }
        } catch {
            return false
        }
    }

    func restore() async {
        try? await AppStore.sync()
        await refreshSubscriptionStatus()
    }

    // MARK: - 交易监听（续订、退款、跨设备同步）

    private func observeTransactionUpdates() -> Task<Void, Never> {
        Task(priority: .background) { [weak self] in
            for await update in Transaction.updates {
                if case .verified(let transaction) = update {
                    await transaction.finish()
                }
                await self?.refreshSubscriptionStatus()
            }
        }
    }
}
