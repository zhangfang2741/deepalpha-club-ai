import SwiftUI
import StoreKit

/// 方案卡上的一条权益。
private struct PlanFeature: Identifiable {
    let icon: String
    let title: String
    let desc: String
    var id: String { title }
}

/// 订阅付费墙。展示两档方案（体验版 / 高级版）的权益、价格与免费试用，
/// 并含自动续订披露与条款/隐私链接（苹果要求）。
struct PaywallView: View {
    @EnvironmentObject var store: StoreManager
    @Environment(\.dismiss) private var dismiss
    @State private var restoring = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 22) {
                    header
                    content
                    restoreButton
                    legal
                }
                .padding(20)
            }
            .background(Theme.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Image(systemName: "xmark").font(.footnote.bold()) }
                        .accessibilityLabel(L("关闭"))
                        .tint(Theme.textSecondary)
                }
            }
            // tier 变化（购买/恢复成功）即关闭；已订阅体验版再升级高级版时 isSubscribed
            // 本就是 true，必须看 tier 本身的变化才能在升级完成后自动收起付费墙。
            .onChange(of: store.tier) { _, _ in dismiss() }
        }
        // 付费墙不参与截图分享：订阅价格与权益文案带法务口径，截出去容易被
        // 脱离上下文传播；且它常从「我的」页弹出，抑制声明与呈现路径无关才可靠。
        .suppressScreenshotShare()
    }

    private var header: some View {
        VStack(spacing: 10) {
            Image(systemName: "crown.fill")
                .font(.system(size: 40)).foregroundStyle(Theme.segment)
            Text(L("DeepAlpha 会员"))
                .font(.title.bold()).foregroundColor(Theme.textPrimary)
            Text(L("解锁全部缠论分析，突破每日 %lld 次限制", AppConfig.freeDailyQuota))
                .font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private var content: some View {
        if store.experienceProduct != nil || store.premiumProduct != nil {
            VStack(spacing: 16) {
                if let premium = store.premiumProduct {
                    planCard(
                        product: premium, planName: L("高级版"), badge: L("推荐"),
                        features: [
                            PlanFeature(icon: "infinity", title: L("无限次缠论分析"), desc: L("不再受每日次数限制")),
                            PlanFeature(icon: "dot.radiowaves.left.and.right", title: L("信号雷达"),
                                        desc: L("扫描科技指数成分股，每日买卖点一图看全")),
                            PlanFeature(icon: "scope", title: L("30 分钟次级别确认"),
                                        desc: L("日线定方向、30 分钟找进出点，共振/逆势一眼分辨")),
                            PlanFeature(icon: "star.fill", title: L("自选批量状态计算"),
                                        desc: L("自选列表批量算出每只标的当前所处的结构阶段")),
                            PlanFeature(icon: "globe.asia.australia.fill", title: L("美股 / A 股 / 港股"),
                                        desc: L("三个市场统一的缠论结构分析")),
                        ])
                }
                if let experience = store.experienceProduct {
                    planCard(
                        product: experience, planName: L("体验版"), badge: nil,
                        features: [
                            PlanFeature(icon: "infinity", title: L("无限次缠论分析"), desc: L("不再受每日次数限制")),
                            PlanFeature(icon: "globe.asia.australia.fill", title: L("美股 / A 股 / 港股"),
                                        desc: L("三个市场统一的缠论结构分析")),
                            // 不写「操作倾向」：付费墙是宣传语境，这四个字等于在卖操作建议，
                            // 正踩 3.1.1 / 5.2.5。口径与 App 内的「形态分析」保持一致。
                            PlanFeature(icon: "flag.fill", title: L("全部买卖点与形态分析"),
                                        desc: L("一二三类买卖点、背驰与加权依据")),
                        ])
                }
            }
        } else if store.loadFailed {
            VStack(spacing: 10) {
                Text(L("暂时无法加载订阅信息")).foregroundColor(Theme.textPrimary)
                Button(L("重试")) { Task { await store.loadProducts() } }
                    .buttonStyle(.bordered).tint(Theme.accent)
            }
            .frame(maxWidth: .infinity).padding()
        } else {
            ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 100)
        }
    }

    /// 一张方案卡：权益列表 + 价格 + 订阅按钮。高级版带「推荐」角标。
    private func planCard(
        product: Product, planName: String, badge: String?, features: [PlanFeature]
    ) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(planName).font(.title3.bold()).foregroundColor(Theme.textPrimary)
                if let badge {
                    Text(badge)
                        .font(.caption2.bold()).foregroundColor(.white)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Theme.segment, in: Capsule())
                }
                Spacer()
            }
            VStack(alignment: .leading, spacing: 10) {
                ForEach(features) { f in feature(f.icon, f.title, f.desc) }
            }
            priceRow(product)
            subscribeButton(product, planName: planName)
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(badge != nil ? Theme.segment.opacity(0.5) : Theme.border, lineWidth: badge != nil ? 1.5 : 1)
        )
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

    private func priceRow(_ product: Product) -> some View {
        HStack {
            if let trial = store.trialPeriodText(product) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(L("%@免费试用", trial)).font(.subheadline.bold()).foregroundColor(Theme.up)
                    Text(L("试用结束后 %@/月，可随时取消", product.displayPrice))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                }
            } else {
                VStack(alignment: .leading, spacing: 2) {
                    Text(L("%@/月", product.displayPrice)).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                    Text(L("可随时取消")).font(.caption2).foregroundColor(Theme.textSecondary)
                }
            }
            Spacer()
        }
        .padding(10)
        .frame(maxWidth: .infinity)
        .background(Theme.accent.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func subscribeButton(_ product: Product, planName: String) -> some View {
        Button {
            Task { await store.purchase(product) }
        } label: {
            HStack {
                if store.purchaseInProgress { ProgressView().tint(.white) }
                Text(store.offersFreeTrial(product)
                     ? L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
                     : L("订阅%@", planName))
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 13)
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
            Text(restoring ? L("恢复中…") : L("恢复购买"))
                .font(.footnote).foregroundColor(Theme.accent)
        }
        .disabled(restoring)
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 8) {
            Text(L("订阅为自动续订。免费试用结束后将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。"))
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 16) {
                Link(L("服务条款"), destination: URL(string: "https://deepalpha.club/terms")!)
                Link(L("隐私政策"), destination: URL(string: "https://deepalpha.club/privacy")!)
            }
            .font(.caption2).tint(Theme.accent)
        }
        .padding(.top, 4)
    }
}
