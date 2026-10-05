import SwiftUI
import StoreKit

/// 付费墙的一项权益：标题 + 一句说明（说清能做什么、和免费版的差别）。
/// 只列订阅后才有的——免费版也能用的（买卖点与形态分析、三个市场）不列，
/// 否则等于把免费功能包装成付费权益（2.3.1，也会让用户觉得被误导）。
private struct Benefit: Identifiable {
    let icon: String
    let title: String
    let detail: String
    var id: String { title }
}

/// 付费墙配色：深色底 + 金色点缀，营造会员质感。
private enum Gold {
    static let light = Color(hex: 0xF8DE9A)
    static let mid = Color(hex: 0xE5B03A)
    static let deep = Color(hex: 0xB9821C)
    static let onGold = Color(hex: 0x1A1204)
    static var gradient: LinearGradient {
        LinearGradient(colors: [light, mid, deep], startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

/// 订阅付费墙。只有一个会员（2026-10-05 起，原基础版 / 高级版合并）：整页固定在一屏内、不滚动，
/// 列出全部权益、价格（有活动价时划线展示正价），并含自动续订披露与条款/隐私链接（苹果要求）。
struct PaywallView: View {
    @EnvironmentObject var store: StoreManager
    @Environment(\.dismiss) private var dismiss
    @State private var restoring = false

    var body: some View {
        GeometryReader { geo in
            // 矮屏（SE 一类）收掉权益的说明行，保证整页不滚动
            let compact = geo.size.height < 720
            ZStack(alignment: .top) {
                Theme.background.ignoresSafeArea()
                RadialGradient(colors: [Gold.mid.opacity(0.22), .clear],
                               center: .top, startRadius: 0, endRadius: 360)
                    .ignoresSafeArea()
                VStack(spacing: 0) {
                    closeBar
                    header(compact: compact)
                    Spacer(minLength: compact ? 8 : 16)
                    content(compact: compact)
                    Spacer(minLength: compact ? 6 : 12)
                    restoreButton
                    legal
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 8)
            }
        }
        // tier 变化（购买/恢复成功）即关闭
        .onChange(of: store.tier) { _, _ in dismiss() }
        // 付费墙不参与截图分享：订阅价格与权益文案带法务口径，截出去容易被
        // 脱离上下文传播；且它常从「我的」页弹出，抑制声明与呈现路径无关才可靠。
        .suppressScreenshotShare()
    }

    private var closeBar: some View {
        HStack {
            Spacer()
            Button { dismiss() } label: {
                Image(systemName: "xmark").font(.footnote.bold())
                    .foregroundColor(Theme.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(Theme.surface.opacity(0.8), in: Circle())
            }
            .accessibilityLabel(L("关闭"))
        }
        .padding(.top, 12)
    }

    private func header(compact: Bool) -> some View {
        VStack(spacing: compact ? 4 : 8) {
            Image(systemName: "crown.fill")
                .font(.system(size: compact ? 30 : 38))
                .foregroundStyle(Gold.gradient)
                .shadow(color: Gold.mid.opacity(0.45), radius: 12)
            Text(L("DeepAlpha 会员"))
                .font(.system(size: compact ? 24 : 28, weight: .bold, design: .serif))
                .foregroundStyle(LinearGradient(colors: [.white, Gold.light], startPoint: .leading, endPoint: .trailing))
            Text(L("不限次分析 · 市场雷达 · 次级别确认"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
    }

    @ViewBuilder
    private func content(compact: Bool) -> some View {
        if let product = store.membershipProduct {
            membershipCard(product, compact: compact)
        } else if store.loadFailed {
            VStack(spacing: 10) {
                Text(L("暂时无法加载订阅信息")).foregroundColor(Theme.textPrimary)
                Button(L("重试")) { Task { await store.loadProducts() } }
                    .buttonStyle(.bordered).tint(Gold.mid)
            }
            .frame(maxWidth: .infinity).padding()
        } else {
            ProgressView().tint(Gold.mid).frame(maxWidth: .infinity, minHeight: 100)
        }
    }

    // MARK: - 权益数据

    /// 与代码里的实际门禁一一对应（改门禁时同步改这里）：
    /// - 不限次分析：免费每日 AppConfig.freeDailyQuota 支不同标的（UsageTracker），会员不限
    /// - 次级别确认（日线×30 分钟、周线×日线）：会员专属（MainTabView.hasSubLevelAccess）
    /// - 每日雷达：会员可看每日真实雷达，免费只有示例日；含近 30 个交易日历史回看
    /// - 自选上限：免费 1 / 会员不限（后端 app/services/watchlist.py TIER_LIMITS）
    /// - 自选结构状态：免费只显示最早加入的 1 支，会员全部（WatchlistViewModel.phase(for:)）
    /// 文案只描述功能本身，不暗示收益或操作建议（3.1.1 / 5.2.5）。
    private var benefits: [Benefit] {
        [
            Benefit(icon: "infinity", title: L("不限次分析"),
                    detail: L("免费版每天 %lld 支", AppConfig.freeDailyQuota)),
            Benefit(icon: "scope", title: L("次级别确认"),
                    detail: L("日线对照 30 分钟，周线对照日线")),
            Benefit(icon: "dot.radiowaves.left.and.right", title: L("每日市场雷达"),
                    detail: L("美股 / A 股 / 港股，免费版仅示例日")),
            Benefit(icon: "clock.arrow.circlepath", title: L("雷达历史回看"),
                    detail: L("回看近 30 个交易日")),
            Benefit(icon: "star.fill", title: L("自选不限数量"),
                    detail: L("免费版最多 1 支")),
            Benefit(icon: "square.stack.3d.up.fill", title: L("全部自选状态"),
                    detail: L("免费版仅显示最早加入的 1 支")),
        ]
    }

    // MARK: - 会员卡

    /// 一张卡：全部权益 + 价格 + 订阅按钮。
    private func membershipCard(_ product: Product, compact: Bool) -> some View {
        VStack(spacing: compact ? 10 : 14) {
            VStack(spacing: 0) {
                ForEach(Array(benefits.enumerated()), id: \.element.id) { idx, benefit in
                    benefitRow(benefit, compact: compact)
                    if idx < benefits.count - 1 {
                        Rectangle().fill(Color.white.opacity(0.06)).frame(height: 0.5)
                            .padding(.leading, 44)
                    }
                }
            }
            priceBlock(product)
            subscribeButton(product)
        }
        .padding(compact ? 12 : 16)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(LinearGradient(colors: [Theme.surface, Theme.background], startPoint: .top, endPoint: .bottom))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(LinearGradient(colors: [Gold.light.opacity(0.7), Gold.deep.opacity(0.25)],
                                       startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1)
        )
        .shadow(color: Gold.mid.opacity(0.12), radius: 20, y: 6)
    }

    private func benefitRow(_ benefit: Benefit, compact: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: benefit.icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Gold.gradient)
                .frame(width: 32)
            VStack(alignment: .leading, spacing: 1) {
                Text(benefit.title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                if !compact {
                    Text(benefit.detail).font(.caption2).foregroundColor(Theme.textSecondary)
                        .lineLimit(1).minimumScaleFactor(0.8)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundColor(Gold.mid)
        }
        .padding(.vertical, compact ? 7 : 9)
        .accessibilityElement(children: .combine)
    }

    /// 划线价只能是真实正价：正价 = product.displayPrice，活动价 = ASC 里配置的推介优惠，
    /// 两者都由 StoreKit 给出，且只对有资格的新订阅者展示。不要在代码里写死「原价」或活动价金额——
    /// 从未按那个价卖过的划线价属于虚构参考价，踩 App Store 2.3.1 / 5.6 与各地价格法。
    private func priceBlock(_ product: Product) -> some View {
        VStack(spacing: 3) {
            if let trial = store.trialPeriodText(product) {
                Text(L("%@免费试用", trial)).font(.headline).foregroundColor(Gold.light)
                Text(L("试用结束后 %@/月，可随时取消", product.displayPrice))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
            } else if let intro = store.introDiscount(product) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(L("活动价"))
                        .font(.system(size: 10, weight: .bold)).foregroundColor(Gold.onGold)
                        .padding(.horizontal, 7).padding(.vertical, 2)
                        .background(Gold.gradient, in: Capsule())
                    Text(intro.priceText)
                        .font(.system(size: 26, weight: .bold, design: .rounded))
                        .foregroundStyle(Gold.gradient)
                    Text(L("%@/月", product.displayPrice))
                        .strikethrough().font(.footnote).foregroundColor(Theme.textSecondary)
                }
                Text(L("活动价%@，之后 %@/月，可随时取消", intro.durationText, product.displayPrice))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
            } else {
                Text(L("%@/月", product.displayPrice))
                    .font(.system(size: 26, weight: .bold, design: .rounded)).foregroundColor(Theme.textPrimary)
                Text(L("可随时取消")).font(.caption2).foregroundColor(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    private func subscribeButton(_ product: Product) -> some View {
        Button {
            Task { await store.purchase(product) }
        } label: {
            HStack {
                if store.purchasingProductID == product.id { ProgressView().tint(Gold.onGold) }
                Text(store.offersFreeTrial(product)
                     ? L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
                     : L("订阅%@", L("会员")))
                    .fontWeight(.bold)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 14)
            .background(Gold.gradient).foregroundColor(Gold.onGold)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .shadow(color: Gold.mid.opacity(0.35), radius: 10, y: 4)
        }
        .disabled(store.purchaseInProgress)
    }

    private var restoreButton: some View {
        Button {
            restoring = true
            Task { await store.restore(); restoring = false }
        } label: {
            Text(restoring ? L("恢复中…") : L("恢复购买"))
                .font(.footnote).foregroundColor(Gold.light.opacity(0.9))
        }
        .disabled(restoring)
        .padding(.bottom, 6)
    }

    /// 当前商品是否带免费试用——目前没配试用期，但披露文案不能写死
    /// 「免费试用结束后」，否则试用期一旦被拿掉（如这次去掉的 3 天试用）文案就说谎；
    /// 以后如果又在 ASC 给某个地区配了试用，也不用记得回来改这行。
    private var anyProductOffersTrial: Bool {
        store.products.contains { store.offersFreeTrial($0) }
    }

    /// 有活动价时的续订披露：写清优惠期多长、之后按什么价续订（3.1.2 要求续订价清楚可见）。
    private var introDisclosure: String? {
        guard let intro = store.products.lazy.compactMap({ store.introDiscount($0) }).first else { return nil }
        return L("活动价仅限首次订阅的 Apple 账户，优惠期（%@）结束后按正价自动续订。", intro.durationText)
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 6) {
            if let introDisclosure {
                Text(introDisclosure)
                    .font(.caption2).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            Text(anyProductOffersTrial
                 ? L("订阅为自动续订。免费试用结束后将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。")
                 : L("订阅为自动续订，将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。"))
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 16) {
                Link(L("服务条款"), destination: URL(string: "https://deepalpha.club/terms")!)
                Link(L("隐私政策"), destination: URL(string: "https://deepalpha.club/privacy")!)
            }
            .font(.caption2).tint(Theme.accent)
        }
    }
}
