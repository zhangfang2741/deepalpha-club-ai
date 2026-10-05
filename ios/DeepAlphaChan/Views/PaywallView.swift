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

/// 订阅付费墙。只有一个会员（2026-10-05 起，原基础版 / 高级版合并）。
///
/// 版面（上到下）：皇冠 + 标题 → **价格卡（大字，一眼看到多少钱）** → 权益列表 → 恢复购买 / 续订披露 / 条款；
/// 订阅按钮固定在屏幕底部（按钮上直接写价格），不用滑到底才找得到。价格、自动续订披露、恢复购买、条款 / 隐私链接
/// 都在（苹果要求）。
struct PaywallView: View {
    @EnvironmentObject var store: StoreManager
    @Environment(\.dismiss) private var dismiss
    @State private var restoring = false

    /// 金色系：皇冠、价格、订阅按钮共用，整页只用这一个强调色（权益图标也用它的淡色），看着更统一、更有质感。
    private static let goldLight = Color(hex: 0xFDE9A9)
    private static let gold = Color(hex: 0xF5B93B)
    private static let goldDeep = Color(hex: 0xE59A12)
    private static let goldGradient = LinearGradient(
        colors: [goldLight, gold], startPoint: .top, endPoint: .bottom)

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    header
                    content
                    if store.membershipProduct != nil { benefitsCard }
                    restoreButton
                    legal
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 24)
            }
            .background(background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: { Image(systemName: "xmark").font(.footnote.bold()) }
                        .accessibilityLabel(L("关闭"))
                        .tint(Theme.textSecondary)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if let product = store.membershipProduct { bottomBar(product) }
            }
            // tier 变化（购买/恢复成功）即关闭
            .onChange(of: store.tier) { _, _ in dismiss() }
        }
        // 付费墙不参与截图分享：订阅价格与权益文案带法务口径，截出去容易被
        // 脱离上下文传播；且它常从「我的」页弹出，抑制声明与呈现路径无关才可靠。
        .suppressScreenshotShare()
    }

    /// 底色：深色 + 顶部一团很淡的金色光晕，比纯黑底有层次。
    private var background: some View {
        ZStack(alignment: .top) {
            Theme.background
            RadialGradient(colors: [Self.gold.opacity(0.16), .clear],
                           center: .top, startRadius: 0, endRadius: 360)
                .frame(height: 360)
        }
        .ignoresSafeArea()
    }

    private var header: some View {
        VStack(spacing: 12) {
            Image(systemName: "crown.fill")
                .font(.system(size: 30))
                .foregroundStyle(Self.goldGradient)
                .frame(width: 68, height: 68)
                .background(Self.gold.opacity(0.12), in: Circle())
                .overlay(Circle().stroke(Self.gold.opacity(0.45), lineWidth: 1))
                .shadow(color: Self.gold.opacity(0.35), radius: 18)
            Text(L("DeepAlpha 会员"))
                .font(.system(size: 28, weight: .bold)).foregroundColor(Theme.textPrimary)
            Text(L("不限次分析 · 市场雷达 · 次级别确认"))
                .font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 4)
    }

    @ViewBuilder
    private var content: some View {
        if let product = store.membershipProduct {
            priceCard(product)
        } else if store.loadFailed {
            VStack(spacing: 10) {
                Text(L("暂时无法加载订阅信息")).foregroundColor(Theme.textPrimary)
                Button(L("重试")) { Task { await store.loadProducts() } }
                    .buttonStyle(.bordered).tint(Theme.accent)
                if let reason = store.loadDiagnostic {
                    Text(reason)
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                        .textSelection(.enabled)
                }
            }
            .frame(maxWidth: .infinity).padding()
        } else {
            ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 100)
        }
    }

    // MARK: - 价格卡

    /// 价格是整页最大的字。划线价只能是真实正价：正价 = product.displayPrice，新客价 = ASC 里配置的推介优惠，
    /// 两者都由 StoreKit 给出，且只对有资格的新客展示。不要在代码里写死「原价」倍数——
    /// 从未按那个价卖过的划线价属于虚构参考价，踩 App Store 2.3.1 / 5.6 与各地价格法。
    private func priceCard(_ product: Product) -> some View {
        VStack(spacing: 8) {
            if let trial = store.trialPeriodText(product) {
                badge(L("%@免费试用", trial))
                priceLine(product.displayPrice)
                caption(L("试用结束后 %@/月，可随时取消", product.displayPrice))
            } else if let intro = store.introDiscount(product) {
                badge(L("新客%@", intro.durationText))
                priceLine(intro.priceText, showsUnit: false)
                Text(L("%@/月", product.displayPrice))
                    .strikethrough().font(.footnote).foregroundColor(Theme.textSecondary)
                caption(L("新客专享%@，之后 %@/月，可随时取消", intro.durationText, product.displayPrice))
            } else {
                priceLine(product.displayPrice)
                caption(L("自动续订 · 可随时取消"))
            }
        }
        .padding(.vertical, 22)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(colors: [Self.gold.opacity(0.14), Theme.surface],
                           startPoint: .top, endPoint: .bottom),
            in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Self.gold.opacity(0.5), lineWidth: 1))
    }

    /// 大字价格 +「/月」。价格串直接用 StoreKit 的 displayPrice（带币种符号与本地化格式），不自己拼；
    /// 新客价的串（`introDiscount.priceText`）自带「/月」，不再重复加。
    private func priceLine(_ price: String, showsUnit: Bool = true) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(price)
                .font(.system(size: 46, weight: .bold, design: .rounded))
                .foregroundStyle(Self.goldGradient)
                .minimumScaleFactor(0.6).lineLimit(1)
            if showsUnit {
                Text(L("/月")).font(.title3.weight(.semibold)).foregroundColor(Theme.textSecondary)
            }
        }
    }

    private func badge(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11, weight: .bold)).foregroundColor(Theme.background)
            .padding(.horizontal, 10).padding(.vertical, 3)
            .background(Self.goldGradient, in: Capsule())
    }

    private func caption(_ text: String) -> some View {
        Text(text).font(.caption).foregroundColor(Theme.textSecondary)
            .multilineTextAlignment(.center).padding(.horizontal, 16)
    }

    // MARK: - 权益

    /// 与代码里的实际门禁一一对应（改门禁时同步改这里）：
    /// - 不限次分析：免费每日 AppConfig.freeDailyQuota 支不同标的（UsageTracker），会员不限
    /// - 次级别确认（日线×30 分钟、周线×日线）：会员专属（MainTabView.hasSubLevelAccess）
    /// - 每日雷达：会员可看每日真实雷达，免费只有示例日；含近 30 个交易日历史回看
    /// - 自选上限：免费 1 / 会员不限（后端 app/services/watchlist.py TIER_LIMITS）
    /// - 自选结构状态：免费只显示最早加入的 1 支，会员全部（WatchlistViewModel.phase(for:)）
    /// 文案只描述功能本身，不暗示收益或操作建议（3.1.1 / 5.2.5）。每条一行说明，尽量短。
    private var benefits: [Benefit] {
        [
            Benefit(icon: "infinity", title: L("不限次分析"),
                    detail: L("免费版每天 %lld 支标的", AppConfig.freeDailyQuota)),
            Benefit(icon: "scope", title: L("次级别确认"),
                    detail: L("日线对照 30 分钟，周线对照日线")),
            Benefit(icon: "dot.radiowaves.left.and.right", title: L("每日市场雷达"),
                    detail: L("美股 / A 股 / 港股主要指数，免费版仅示例日")),
            Benefit(icon: "clock.arrow.circlepath", title: L("雷达历史回看"),
                    detail: L("回看近 30 个交易日")),
            Benefit(icon: "star.fill", title: L("自选不限数量"),
                    detail: L("免费版最多 1 支")),
            Benefit(icon: "square.stack.3d.up.fill", title: L("全部自选状态"),
                    detail: L("结构阶段与最新信号，免费版仅 1 支")),
        ]
    }

    private var benefitsCard: some View {
        VStack(spacing: 0) {
            ForEach(Array(benefits.enumerated()), id: \.element.id) { i, benefit in
                HStack(spacing: 14) {
                    Image(systemName: benefit.icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Self.gold)
                        .frame(width: 32, height: 32)
                        .background(Self.gold.opacity(0.12), in: RoundedRectangle(cornerRadius: 9))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(benefit.title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                        Text(benefit.detail).font(.caption).foregroundColor(Theme.textSecondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "checkmark").font(.caption.weight(.bold)).foregroundColor(Self.gold)
                }
                .padding(.vertical, 11)
                .accessibilityElement(children: .combine)
                if i < benefits.count - 1 { Divider().overlay(Theme.border).padding(.leading, 46) }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 4)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Theme.border, lineWidth: 1))
    }

    // MARK: - 底部订阅栏

    /// 固定在屏幕底部：按钮上直接写价格，滑到哪里都能订阅，也不会「找不到多少钱」。
    private func bottomBar(_ product: Product) -> some View {
        VStack(spacing: 6) {
            Button {
                Task { await store.purchase(product) }
            } label: {
                HStack(spacing: 8) {
                    if store.purchasingProductID == product.id { ProgressView().tint(Theme.background) }
                    Text(buttonTitle(product)).font(.system(size: 17, weight: .bold))
                }
                .frame(maxWidth: .infinity).padding(.vertical, 15)
                .background(
                    LinearGradient(colors: [Self.gold, Self.goldDeep], startPoint: .top, endPoint: .bottom),
                    in: RoundedRectangle(cornerRadius: 16))
                .foregroundColor(Theme.background)
                .shadow(color: Self.gold.opacity(0.3), radius: 12, y: 4)
            }
            .disabled(store.purchaseInProgress)
            Text(L("自动续订 · 可随时取消"))
                .font(.caption2).foregroundColor(Theme.textSecondary)
        }
        .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 8)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) { Divider().overlay(Theme.border) }
    }

    /// 按钮文案：有试用写试用，有新客价写新客价，否则写「订阅会员 · 正价/月」——价格永远在按钮上。
    private func buttonTitle(_ product: Product) -> String {
        if store.offersFreeTrial(product) {
            return L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
        }
        if let intro = store.introDiscount(product) {
            return L("订阅会员 · %@", intro.priceText)
        }
        return L("订阅会员 · %@/月", product.displayPrice)
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

    /// 当前商品是否带免费试用——目前没配试用期，但披露文案不能写死
    /// 「免费试用结束后」，否则试用期一旦被拿掉（如这次去掉的 3 天试用）文案就说谎；
    /// 以后如果又在 ASC 给某个地区配了试用，也不用记得回来改这行。
    private var anyProductOffersTrial: Bool {
        store.products.contains { store.offersFreeTrial($0) }
    }

    /// 有新客价时的续订披露：写清优惠期多长、之后按什么价续订（3.1.2 要求续订价清楚可见）。
    private var introDisclosure: String? {
        guard let intro = store.products.lazy.compactMap({ store.introDiscount($0) }).first else { return nil }
        return L("新客专享价仅限首次订阅的 Apple 账户，优惠期（%@）结束后按正价自动续订。", intro.durationText)
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 8) {
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
        .padding(.top, 4)
    }
}
