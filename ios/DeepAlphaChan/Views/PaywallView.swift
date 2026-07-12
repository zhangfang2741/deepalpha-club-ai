import SwiftUI
import StoreKit

/// 订阅付费墙。展示权益、价格、7 天免费试用，并含自动续订披露与条款/隐私链接（苹果要求）。
struct PaywallView: View {
    @EnvironmentObject var store: StoreManager
    @Environment(\.dismiss) private var dismiss
    @State private var restoring = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    header
                    featureList
                    content
                    legal
                }
                .padding(20)
            }
            .background(Theme.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Image(systemName: "xmark").font(.footnote.bold()) }
                        .tint(Theme.textSecondary)
                }
            }
            .onChange(of: store.isSubscribed) { _, subscribed in
                if subscribed { dismiss() }
            }
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            Image(systemName: "crown.fill")
                .font(.system(size: 40)).foregroundStyle(Theme.segment)
            Text("DeepAlpha Pro")
                .font(.title.bold()).foregroundColor(Theme.textPrimary)
            Text("解锁全部缠论分析，突破每日 \(AppConfig.freeDailyQuota) 次限制")
                .font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    private var featureList: some View {
        VStack(alignment: .leading, spacing: 12) {
            feature("infinity", "无限次缠论分析", "不再受每日次数限制")
            feature("arrow.triangle.branch", "结构 GAP 分析", "市场结构 × 产业结构的 AI 背离洞察")
            feature("flag.fill", "全部买卖点与操作倾向", "一二三类买卖点、背驰与依据")
            feature("bolt.fill", "优先体验新功能", "后续模块优先向会员开放")
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func feature(_ icon: String, _ title: String, _ desc: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).foregroundColor(Theme.accent).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                Text(desc).font(.caption).foregroundColor(Theme.textSecondary)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let product = store.monthlyProduct {
            VStack(spacing: 14) {
                priceCard(product)
                subscribeButton(product)
                restoreButton
            }
        } else if store.loadFailed {
            VStack(spacing: 10) {
                Text("暂时无法加载订阅信息").foregroundColor(Theme.textPrimary)
                Button("重试") { Task { await store.loadProducts() } }
                    .buttonStyle(.bordered).tint(Theme.accent)
            }
            .frame(maxWidth: .infinity).padding()
        } else {
            ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 100)
        }
    }

    private func priceCard(_ product: Product) -> some View {
        VStack(spacing: 6) {
            if store.offersFreeTrial {
                Text("7 天免费试用").font(.title3.bold()).foregroundColor(Theme.up)
                Text("试用结束后 \(product.displayPrice)/月，可随时取消")
                    .font(.footnote).foregroundColor(Theme.textSecondary)
            } else {
                Text("\(product.displayPrice)/月").font(.title3.bold()).foregroundColor(Theme.textPrimary)
                Text("可随时取消").font(.footnote).foregroundColor(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity).padding(16)
        .background(Theme.accent.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func subscribeButton(_ product: Product) -> some View {
        Button {
            Task { await store.purchase(product) }
        } label: {
            HStack {
                if store.purchaseInProgress { ProgressView().tint(.white) }
                Text(store.offersFreeTrial ? "开始 7 天免费试用" : "订阅 Pro")
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 15)
            .background(Theme.accent).foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .disabled(store.purchaseInProgress)
    }

    private var restoreButton: some View {
        Button {
            restoring = true
            Task { await store.restore(); restoring = false }
        } label: {
            Text(restoring ? "恢复中…" : "恢复购买")
                .font(.footnote).foregroundColor(Theme.accent)
        }
        .disabled(restoring)
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 8) {
            Text("订阅为自动续订。免费试用结束后将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。")
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 16) {
                Link("服务条款", destination: URL(string: "https://deepalpha.club/terms")!)
                Link("隐私政策", destination: URL(string: "https://deepalpha.club/privacy")!)
            }
            .font(.caption2).tint(Theme.accent)
        }
        .padding(.top, 4)
    }
}
