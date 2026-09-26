import Foundation
import StoreKit

/// 订阅层级：免费 < 基础版（解锁全量缠论分析）< 高级版
/// （基础版权益 + 次级别确认 / 信号雷达 / 自选批量状态计算）。数值越大权益越高，`max` 取较高档
/// 即可判定「拥有该档或以上」。
enum SubscriptionTier: Int, Comparable {
    case free = 0
    case experience = 1
    case premium = 2

    static func < (lhs: SubscriptionTier, rhs: SubscriptionTier) -> Bool { lhs.rawValue < rhs.rawValue }

    /// 传给后端的档位字符串（如自选上限按档位区分，见 app/services/watchlist.py
    /// 的 TIER_LIMITS）。"experience" 是历史命名，对外/对接口统一叫 "basic"。
    var apiValue: String {
        switch self {
        case .free: return "free"
        case .experience: return "basic"
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
    @Published private(set) var tier: SubscriptionTier = .free
    @Published var purchaseInProgress = false
    @Published private(set) var loadFailed = false

    private var updatesTask: Task<Void, Never>?

    init() {
        updatesTask = observeTransactionUpdates()
        Task {
            await loadProducts()
            await refreshSubscriptionStatus()
        }
    }

    deinit { updatesTask?.cancel() }

    /// 是否拥有任一档订阅（基础版或高级版）：解锁无限次缠论分析。
    var isSubscribed: Bool { tier != .free }
    /// 是否拥有高级版：额外解锁次级别确认、信号雷达、自选批量状态计算。
    var isPremium: Bool { tier == .premium }

    /// 基础版月度订阅商品。
    var experienceProduct: Product? {
        products.first { $0.id == AppConfig.experienceMonthlyProductID }
    }
    /// 高级版月度订阅商品。
    var premiumProduct: Product? {
        products.first { $0.id == AppConfig.premiumMonthlyProductID }
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

    func loadProducts() async {
        do {
            let items = try await Product.products(for: [
                AppConfig.experienceMonthlyProductID, AppConfig.premiumMonthlyProductID,
            ])
            products = items
            loadFailed = items.isEmpty
            await refreshIntroEligibility()
        } catch {
            loadFailed = true
        }
    }

    /// 两档在同一订阅群组，资格是群组级的，查任一商品即可。
    private func refreshIntroEligibility() async {
        guard let subscription = products.first?.subscription else {
            isEligibleForIntroOffer = false
            return
        }
        isEligibleForIntroOffer = await subscription.isEligibleForIntroOffer
    }

    /// 遍历当前有效权益，判断订阅层级：两档都在有效期内（如降级过渡期）时取更高档。
    func refreshSubscriptionStatus() async {
        var highest: SubscriptionTier = .free
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result, transaction.revocationDate == nil
            else { continue }
            switch transaction.productID {
            case AppConfig.premiumMonthlyProductID:
                highest = max(highest, .premium)
            case AppConfig.experienceMonthlyProductID:
                highest = max(highest, .experience)
            default:
                continue
            }
        }
        tier = highest
        // 买过一次（含用了新客价）资格就没了，购买/续订/跨设备同步后都要重新判定
        await refreshIntroEligibility()
    }

    // MARK: - 购买与恢复

    @discardableResult
    func purchase(_ product: Product) async -> Bool {
        purchaseInProgress = true
        defer { purchaseInProgress = false }
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
