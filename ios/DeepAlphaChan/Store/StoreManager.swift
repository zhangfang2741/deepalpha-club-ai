import Foundation
import StoreKit

/// 订阅层级：免费 < 基础版（解锁全量缠论分析 + 30 分钟次级别确认）< 高级版
/// （基础版权益 + 信号雷达 / 自选批量状态计算）。数值越大权益越高，`max` 取较高档
/// 即可判定「拥有该档或以上」。
enum SubscriptionTier: Int, Comparable {
    case free = 0
    case experience = 1
    case premium = 2

    static func < (lhs: SubscriptionTier, rhs: SubscriptionTier) -> Bool { lhs.rawValue < rhs.rawValue }
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

    /// 是否拥有任一档订阅（基础版或高级版）：解锁无限次缠论分析 + 30 分钟次级别确认。
    var isSubscribed: Bool { tier != .free }
    /// 是否拥有高级版：额外解锁信号雷达、自选批量状态计算。
    var isPremium: Bool { tier == .premium }

    /// 基础版月度订阅商品。
    var experienceProduct: Product? {
        products.first { $0.id == AppConfig.experienceMonthlyProductID }
    }
    /// 高级版月度订阅商品。
    var premiumProduct: Product? {
        products.first { $0.id == AppConfig.premiumMonthlyProductID }
    }

    /// 某个订阅商品当前是否有资格享受免费试用（用于文案：「开始 N 天免费试用」）。
    func offersFreeTrial(_ product: Product) -> Bool {
        product.subscription?.introductoryOffer?.paymentMode == .freeTrial
    }

    /// 免费试用时长文案（如「3 天」）：直接读商品在 App Store Connect / Configuration.storekit
    /// 里的实际配置，不在代码里硬编码天数——试用时长以后只改配置就行，不用跟着改文案。
    func trialPeriodText(_ product: Product) -> String? {
        guard let offer = product.subscription?.introductoryOffer, offer.paymentMode == .freeTrial
        else { return nil }
        return Self.periodText(offer.period)
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
        } catch {
            loadFailed = true
        }
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
