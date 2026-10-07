import SwiftUI
import StoreKit

/// 免费版 vs 会员的一行对比。`free` 为 nil 表示免费版没有这项（显示锁）；`member` 为 nil 表示会员有（显示对勾），
/// 有具体额度时写文字。只列订阅后才有差异的——免费版也能用的（买卖点与形态分析、三个市场）不列，
/// 否则等于把免费功能包装成付费权益（2.3.1，也会让用户觉得被误导）。
private struct CompareRow: Identifiable {
    let icon: String
    let title: String
    var free: String? = nil
    var member: String? = nil
    var id: String { title }
}

/// 订阅付费墙。只有一个会员（2026-10-05 起，原基础版 / 高级版合并）。
///
/// 版面（上到下）：皇冠 + 标题 → **价格卡（大字）** → **免费版 vs 会员对比表**（会员列高亮，免费版缺的用锁标出）→
/// 恢复购买 / 续订披露 / 条款；订阅按钮固定在屏幕底部（按钮上直接写价格）。
/// 配色与全 App 统一：主题蓝 `Theme.accent` 作强调色，皇冠沿用 App 里其他地方的琥珀色（`Theme.segment`）。
/// 价格、自动续订披露、恢复购买、条款 / 隐私链接都在（苹果要求）。
struct PaywallView: View {
    @EnvironmentObject var store: StoreManager
    @Environment(\.dismiss) private var dismiss
    @State private var restoring = false

    /// 对比表两列的宽度：免费版 / 会员。
    private static let columnWidth: CGFloat = 78
    /// 卡片 / 按钮的圆角：小而统一（8pt）。大圆角显得松垮、不精致。
    private static let cornerRadius: CGFloat = 8

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    header
                    content
                    if store.membershipProduct != nil { compareCard }
                    legal
                }
                .padding(.horizontal, 20)
                .padding(.top, 4)
                .padding(.bottom, 12)
            }
            // 整页压到一屏内（常见机型不用上下滑）：内容放得下时不弹性、不显示滚动条；
            // 只有很小的屏幕才会真的滚动，作为兜底，不会把内容截掉
            .scrollBounceBehavior(.basedOnSize)
            .scrollIndicators(.hidden)
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
        .presentationCornerRadius(14)
        // 付费墙不参与截图分享：订阅价格与权益文案带法务口径，截出去容易被
        // 脱离上下文传播；且它常从「我的」页弹出，抑制声明与呈现路径无关才可靠。
        .suppressScreenshotShare()
    }

    /// 底色：App 统一的深色 + 顶部一团很淡的主题蓝光晕。
    private var background: some View {
        ZStack(alignment: .top) {
            Theme.background
            RadialGradient(colors: [Theme.accent.opacity(0.16), .clear],
                           center: .top, startRadius: 0, endRadius: 360)
                .frame(height: 360)
        }
        .ignoresSafeArea()
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "crown.fill")
                .font(.system(size: 22))
                .foregroundStyle(Theme.segment)
                .frame(width: 48, height: 48)
                .background(Theme.segment.opacity(0.12), in: Circle())
                .overlay(Circle().stroke(Theme.segment.opacity(0.4), lineWidth: 1))
            Text(L("DeepAlpha 会员"))
                .font(.system(size: 24, weight: .bold)).foregroundColor(Theme.textPrimary)
        }
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
                // 诊断信息（商品 ID、「协议可能还没生效」）只给开发调试看：发布包里露给用户 / 审核员像半成品（2.1）
                #if DEBUG
                if let reason = store.loadDiagnostic {
                    Text(reason)
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                        .textSelection(.enabled)
                }
                #endif
            }
            .frame(maxWidth: .infinity).padding()
        } else {
            ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 100)
        }
    }

    // MARK: - 价格卡

    /// 价格是整页最大的字。划线价只能是真实正价：正价 = product.displayPrice，活动价 = ASC 里配置的入门优惠（Introductory Offer，只对首次订阅的 Apple 账户生效），
    /// 两者都由 StoreKit 给出，且只对有资格的新客展示。不要在代码里写死「原价」倍数——
    /// 从未按那个价卖过的划线价属于虚构参考价，踩 App Store 2.3.1 / 5.6 与各地价格法。
    private func priceCard(_ product: Product) -> some View {
        VStack(spacing: 6) {
            if let trial = store.trialPeriodText(product) {
                badge(L("%@免费试用", trial))
                priceLine(product.displayPrice)
                caption(L("试用结束后 %@/月，可随时取消", product.displayPrice))
            } else if let intro = store.introDiscount(product) {
                badge(L("活动价 · %@", intro.durationText))
                // 活动价大字 + 同一行右边的划线正价，省一行高度
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    priceLine(intro.priceText, showsUnit: false)
                    Text(L("%@/月", product.displayPrice))
                        .strikethrough().font(.footnote).foregroundColor(Theme.textSecondary)
                }
                caption(L("活动价仅限首次订阅，%@后 %@/月自动续订，可随时取消", intro.durationText, product.displayPrice))
            } else {
                priceLine(product.displayPrice)
                caption(L("自动续订 · 可随时取消"))
            }
        }
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(colors: [Theme.accent.opacity(0.10), Theme.surface],
                           startPoint: .top, endPoint: .bottom),
            in: RoundedRectangle(cornerRadius: Self.cornerRadius))
        .overlay(RoundedRectangle(cornerRadius: Self.cornerRadius).stroke(Theme.accent.opacity(0.45), lineWidth: 0.5))
    }

    /// 大字价格 +「/月」。价格串直接用 StoreKit 的 displayPrice（带币种符号与本地化格式），不自己拼；
    /// 新客价的串（`introDiscount.priceText`）自带「/月」，不再重复加。
    private func priceLine(_ price: String, showsUnit: Bool = true) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(price)
                .font(.system(size: 40, weight: .bold, design: .rounded))
                .foregroundColor(Theme.textPrimary)
                .minimumScaleFactor(0.6).lineLimit(1)
            if showsUnit {
                Text(L("/月")).font(.title3.weight(.semibold)).foregroundColor(Theme.textSecondary)
            }
        }
    }

    private func badge(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11, weight: .bold)).foregroundColor(.white)
            .padding(.horizontal, 10).padding(.vertical, 3)
            .background(Theme.accent, in: RoundedRectangle(cornerRadius: 3))
    }

    private func caption(_ text: String) -> some View {
        Text(text).font(.caption2).foregroundColor(Theme.textSecondary)
            .multilineTextAlignment(.center).padding(.horizontal, 16)
    }

    // MARK: - 免费版 vs 会员

    /// 与代码里的实际门禁一一对应（改门禁时同步改这里）：
    /// - 分析次数：免费每日 AppConfig.freeDailyQuota 支不同标的（UsageTracker），会员不限
    /// - 次级别确认（日线×30 分钟、周线×日线）：会员专属，免费版只有示例股能看（MainTabView.hasSubLevelAccess、isSampleSymbol）
    /// - 每日雷达：会员可看每日真实雷达，免费只有示例日
    /// - 雷达历史回看：会员近 30 个交易日，免费没有
    /// - 基本面名单：会员专属（SignalRadarView 的「名单」按钮只对会员显示）
    /// - 自选上限：免费 1 / 会员不限（后端 app/services/watchlist.py TIER_LIMITS）
    /// - 自选结构状态：免费只显示最早加入的 1 支，会员全部（WatchlistViewModel.phase(for:)）
    /// 文案只描述功能本身，不暗示收益或操作建议（3.1.1 / 5.2.5）；对比只写真实差别，不夸大。
    private var rows: [CompareRow] {
        [
            CompareRow(icon: "infinity", title: L("分析次数"),
                       free: L("%lld 支/天", AppConfig.freeDailyQuota), member: L("不限")),
            CompareRow(icon: "scope", title: L("次级别确认"), free: L("仅示例股")),
            CompareRow(icon: "dot.radiowaves.left.and.right", title: L("每日市场雷达"), free: L("仅示例日")),
            CompareRow(icon: "clock.arrow.circlepath", title: L("雷达历史回看"), member: L("%lld 个交易日", 30)),
            CompareRow(icon: "list.bullet.rectangle", title: L("基本面名单")),
            CompareRow(icon: "star.fill", title: L("自选数量"), free: L("%lld 支", 1), member: L("不限")),
            CompareRow(icon: "square.stack.3d.up.fill", title: L("自选状态"),
                       free: L("%lld 支", 1), member: L("全部")),
        ]
    }

    /// 并排对比：会员列整列高亮（主题蓝底 + 描边）、免费版列整体调暗，缺的能力用锁标出——
    /// 一眼看到「订阅后多了什么」。
    private var compareCard: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                Text(L("免费版与会员对比")).font(.caption.weight(.semibold)).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(L("免费版")).font(.caption.weight(.semibold)).foregroundColor(Theme.textSecondary)
                    .frame(width: Self.columnWidth)
                Text(L("会员")).font(.subheadline.weight(.bold)).foregroundColor(.white)
                    .frame(width: Self.columnWidth)
            }
            .padding(.bottom, 6)

            ForEach(Array(rows.enumerated()), id: \.element.id) { i, row in
                HStack(spacing: 0) {
                    HStack(spacing: 10) {
                        Image(systemName: row.icon)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(Theme.accent)
                            .frame(width: 26, height: 26)
                            .background(Theme.accent.opacity(0.14), in: RoundedRectangle(cornerRadius: 4))
                        Text(row.title).font(.subheadline.weight(.medium)).foregroundColor(Theme.textPrimary)
                            .lineLimit(1).minimumScaleFactor(0.8)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    freeCell(row.free).frame(width: Self.columnWidth)
                    memberCell(row.member).frame(width: Self.columnWidth)
                }
                .padding(.vertical, 8)
                .accessibilityElement(children: .combine)
                if i < rows.count - 1 { Divider().overlay(Theme.border) }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(alignment: .trailing) { memberColumnHighlight }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Self.cornerRadius))
        .overlay(RoundedRectangle(cornerRadius: Self.cornerRadius).stroke(Theme.border, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: Self.cornerRadius))
    }

    /// 会员列的高亮底：贴着卡片右侧，盖住整列（含表头），比卡片内边距略宽。
    private var memberColumnHighlight: some View {
        // 平的半透明底 + 细边，不再用大圆角渐变块：克制、不抢戏
        RoundedRectangle(cornerRadius: 3)
            .fill(Theme.accent.opacity(0.22))
            .overlay(RoundedRectangle(cornerRadius: 3).stroke(Theme.accent.opacity(0.6), lineWidth: 0.5))
            .frame(width: Self.columnWidth + 8)
            .padding(.trailing, 12)
            .padding(.vertical, 6)
            .zIndex(-1)
    }

    /// 免费版单元格：有额度写调暗的文字；没有这项显示锁。
    @ViewBuilder
    private func freeCell(_ value: String?) -> some View {
        if let value {
            Text(value).font(.footnote).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center).lineLimit(1).minimumScaleFactor(0.8)
        } else {
            Image(systemName: "lock.fill").font(.system(size: 13)).foregroundColor(Theme.textSecondary.opacity(0.55))
        }
    }

    /// 会员单元格：有具体额度写白色粗体；其余是对勾。
    @ViewBuilder
    private func memberCell(_ value: String?) -> some View {
        if let value {
            Text(value).font(.footnote.weight(.bold)).foregroundColor(.white)
                .multilineTextAlignment(.center).lineLimit(1).minimumScaleFactor(0.8)
        } else {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 18)).foregroundColor(.white)
        }
    }

    // MARK: - 底部订阅栏

    /// 固定在屏幕底部：按钮上直接写价格，滑到哪里都能订阅，也不会「找不到多少钱」。
    private func bottomBar(_ product: Product) -> some View {
        VStack(spacing: 6) {
            Button {
                Task { await store.purchase(product) }
            } label: {
                HStack(spacing: 8) {
                    if store.purchasingProductID == product.id { ProgressView().tint(.white) }
                    Text(buttonTitle(product)).font(.system(size: 17, weight: .bold))
                }
                .frame(maxWidth: .infinity).padding(.vertical, 15)
                .background(Theme.accent, in: RoundedRectangle(cornerRadius: Self.cornerRadius))
                .foregroundColor(.white)
            }
            .disabled(store.purchaseInProgress)
            Text(footnote(product))
                .font(.caption2).foregroundColor(Theme.textSecondary)
        }
        .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 8)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) { Divider().overlay(Theme.border) }
    }

    /// 按钮下的小字：有活动价时必须写清优惠期过后的价格（3.1.2 要求续订价清楚可见），否则「自动续订 · 可随时取消」。
    private func footnote(_ product: Product) -> String {
        if let intro = store.introDiscount(product) {
            return L("%@后 %@/月自动续订，可随时取消", intro.durationText, product.displayPrice)
        }
        return L("自动续订 · 可随时取消")
    }

    /// 按钮文案：有试用写试用，有新客价写新客价，否则写「订阅会员 · 正价/月」——价格永远在按钮上。
    private func buttonTitle(_ product: Product) -> String {
        if store.offersFreeTrial(product) {
            return L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
        }
        if let intro = store.introDiscount(product) {
            return L("活动价 %@ · 立即订阅", intro.priceText)
        }
        return L("订阅会员 · %@/月", product.displayPrice)
    }

    private var restoreButton: some View {
        Button {
            restoring = true
            Task { await store.restore(); restoring = false }
        } label: {
            Text(restoring ? L("恢复中…") : L("恢复购买"))
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
        return L("活动价仅限首次订阅的 Apple 账户，优惠期（%@）结束后按正价自动续订。", intro.durationText)
    }

    /// 自动续订披露 + 恢复购买 + 条款 / 隐私链接（App Store 审核必备），压成小字一块：
    /// 披露文字在上，下面一行「恢复购买 · 服务条款 · 隐私政策」。
    private var legal: some View {
        VStack(spacing: 6) {
            if let introDisclosure {
                Text(introDisclosure)
                    .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            Text(anyProductOffersTrial
                 ? L("订阅为自动续订。免费试用结束后将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。")
                 : L("订阅为自动续订，将按上述价格自动扣款，除非在当前订阅周期结束前至少 24 小时取消。你可随时在 App Store 账户设置中管理或取消订阅。"))
                .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            HStack(spacing: 14) {
                restoreButton
                Link(L("服务条款"), destination: URL(string: "https://deepalpha.club/terms")!)
                Link(L("隐私政策"), destination: URL(string: "https://deepalpha.club/privacy")!)
            }
            .font(.caption2).tint(Theme.accent)
        }
        .padding(.top, 2)
    }
}
