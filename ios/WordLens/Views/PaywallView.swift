// Views/PaywallView.swift
import SwiftUI
import StoreKit

/// 订阅付费墙。展示权益、价格与自动续订披露，并含条款/隐私链接（苹果要求）。
///
/// 触达点：拍照识别用尽当日 3 次、或学习到第 21 个新词时弹出；设置页也有入口。
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
                .font(.system(size: 40)).foregroundStyle(Theme.fuzzy)
            Text(L("升级 Pro"))
                .font(.title.bold()).foregroundStyle(Theme.textPrimary)
            Text(L("解锁无限拍照识别与学习，专注背单词"))
                .font(.subheadline).foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    private var featureList: some View {
        VStack(alignment: .leading, spacing: 12) {
            feature("camera.fill", L("无限拍照识别"), L("不再受每天 %lld 张的限制", AppConfig.freeDailyPhotoLimit))
            feature("infinity", L("无限学习单词"), L("不再受每天 %lld 个新词的限制", AppConfig.freeDailyWordLimit))
            feature("bolt.fill", L("优先体验新功能"), L("后续新功能优先向会员开放"))
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func feature(_ icon: String, _ title: String, _ desc: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).foregroundStyle(Theme.accent).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.bold()).foregroundStyle(Theme.textPrimary)
                Text(desc).font(.caption).foregroundStyle(Theme.textSecondary)
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
                Text(L("暂时无法加载订阅信息")).foregroundStyle(Theme.textPrimary)
                Button(L("重试")) { Task { await store.loadProducts() } }
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
                Text(L("免费试用")).font(.title3.bold()).foregroundStyle(Theme.known)
                // displayPrice 由 StoreKit 按用户所在地区本地化（含货币符号与金额）。
                Text(L("试用结束后 %@ / 月，可随时取消", product.displayPrice))
                    .font(.footnote).foregroundStyle(Theme.textSecondary)
            } else {
                Text(L("%@ / 月", product.displayPrice)).font(.title3.bold()).foregroundStyle(Theme.textPrimary)
                Text(L("可随时取消")).font(.footnote).foregroundStyle(Theme.textSecondary)
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
                Text(store.offersFreeTrial ? L("开始免费试用") : L("订阅 Pro"))
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 15)
            .background(Theme.accent).foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .disabled(store.purchaseInProgress)
    }

    private var restoreButton: some View {
        Button {
            restoring = true
            Task { await store.restore(); restoring = false }
        } label: {
            Text(restoring ? L("恢复中…") : L("恢复购买"))
                .font(.footnote).foregroundStyle(Theme.accent)
        }
        .disabled(restoring)
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 8) {
            Text(L("订阅为自动续订。到期前将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。"))
                .font(.caption2).foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 16) {
                Link(L("服务条款"), destination: AppConfig.termsOfServiceURL)
                Link(L("隐私政策"), destination: AppConfig.privacyPolicyURL)
            }
            .font(.caption2).tint(Theme.accent)
        }
        .padding(.top, 4)
    }
}
