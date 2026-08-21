// Store/StoreManager.swift
import Foundation
import OSLog
import StoreKit

private let storeLog = Logger(
    subsystem: Bundle.main.bundleIdentifier ?? "club.deepalpha.wordlens",
    category: "storekit"
)

/// 订阅管理：基于 StoreKit 2，端上用加密签名凭证判断订阅状态。
///
/// `Transaction.currentEntitlements` 返回的是 Apple 签名并由系统验签的 JWS，
/// 因此端上判断已具备基本防篡改能力，满足 MVP 需要（服务端校验为后续加固项）。
@MainActor
final class StoreManager: ObservableObject {
    @Published private(set) var products: [Product] = []
    @Published private(set) var isSubscribed = false
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

    /// 月度订阅商品。
    var monthlyProduct: Product? {
        products.first { $0.id == AppConfig.proMonthlyProductID }
    }

    /// 是否处于免费试用资格期（用于文案）。
    var offersFreeTrial: Bool {
        monthlyProduct?.subscription?.introductoryOffer?.paymentMode == .freeTrial
    }

    // MARK: - 加载与状态

    func loadProducts() async {
        do {
            let items = try await Product.products(for: [AppConfig.proMonthlyProductID])
            products = items
            loadFailed = items.isEmpty
            // 空数组是最难查的一种失败：StoreKit 不抛错，只是什么都没返回，
            // 界面直接显示「暂时无法加载订阅信息」而没有任何线索。把已知的
            // 几个成因写进日志，省得下次又从零排查。
            if items.isEmpty {
                storeLog.error("""
                    商品列表为空（未抛错）。依次检查：\
                    ①App Store Connect 的付费应用协议是否为「生效中」；\
                    ②ASC 里的产品 ID 是否与 \(AppConfig.proMonthlyProductID, privacy: .public) 完全一致；\
                    ③订阅是否已提交审核并处于可售状态；\
                    ④本地调试时 Scheme 是否挂了 Products.storekit（该文件里的 identifier \
                    必须是合法 UUID，否则 Xcode 会静默忽略整个配置）
                    """)
            }
        } catch {
            storeLog.error("商品加载失败: \(error.localizedDescription, privacy: .public)")
            loadFailed = true
        }
    }

    /// 遍历当前有效权益，判断月度订阅是否在有效期内。
    func refreshSubscriptionStatus() async {
        var active = false
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result else { continue }
            if transaction.productID == AppConfig.proMonthlyProductID,
               transaction.revocationDate == nil {
                active = true
            }
        }
        isSubscribed = active
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
