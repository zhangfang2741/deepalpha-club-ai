import SwiftUI
import StoreKit

/// 某一档在某项权益上的取值：包含 / 不包含 / 具体额度（如「10 支」）。
private enum TierValue {
    case yes, no
    case text(String)

    var included: Bool {
        if case .no = self { return false }
        return true
    }
}

/// 付费墙的一行权益：对比表与单卡兜底共用同一份数据，保证两处说法一致。
/// 只列订阅后才有的差异——免费版也能用的（买卖点与形态分析、三个市场）不列，
/// 否则等于把免费功能包装成付费权益（2.3.1，也会让用户觉得被误导）。
private struct PlanRow: Identifiable {
    let icon: String
    let title: String
    let basic: TierValue
    let premium: TierValue
    var id: String { title }
}

/// 订阅付费墙。展示两档方案（基础版 / 高级版）的权益、价格与新客优惠，
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
            // tier 变化（购买/恢复成功）即关闭；已订阅基础版再升级高级版时 isSubscribed
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
            Text(L("不限次分析 · 信号雷达 · 次级别确认"))
                .font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private var content: some View {
        if let premium = store.premiumProduct, let experience = store.experienceProduct {
            // 两档并排放成一张对比表，而不是纵向堆叠两张完整卡片——纵向堆叠时
            // 「基础版」整张卡片都在折叠线以下，不下滑很容易根本不知道还有这个
            // 更便宜的档位。并排后两个价格、订阅按钮一屏内同时看见。
            comparisonTable(basic: experience, premium: premium)
        } else if let only = store.premiumProduct ?? store.experienceProduct {
            let isPremium = only.id == AppConfig.premiumMonthlyProductID
            planCard(
                product: only,
                planName: isPremium ? L("高级版") : L("基础版"),
                badge: isPremium ? L("推荐") : nil,
                rows: planRows.filter { (isPremium ? $0.premium : $0.basic).included })
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

    // MARK: - 权益数据

    /// 与代码里的实际门禁一一对应（改门禁时同步改这里）：
    /// - 分析次数：免费每日 AppConfig.freeDailyQuota 支不同标的（UsageTracker），订阅后不限
    /// - 自选上限：免费 1 / 基础 10 / 高级不限（后端 app/services/watchlist.py TIER_LIMITS）
    /// - 自选结构状态：非高级版只显示最早加入的 1 支（WatchlistViewModel.phase(for:)）
    /// - 信号雷达：仅高级版可看每日真实雷达，其余只有示例日
    /// - 次级别确认（日线×30 分钟、周线×日线）：仅高级版（MainTabView.hasSubLevelAccess）
    /// 文案只描述功能本身，不暗示收益或操作建议（3.1.1 / 5.2.5）。
    private var planRows: [PlanRow] {
        [
            PlanRow(icon: "infinity", title: L("不限次分析"),
                    basic: .yes, premium: .yes),
            // 自选股数量 / 其中能看结构状态的数量，合成一行
            PlanRow(icon: "star.fill", title: L("自选股 / 状态"),
                    basic: .text("10 / 1"), premium: .text(L("不限 / 不限"))),
            PlanRow(icon: "dot.radiowaves.left.and.right", title: L("信号雷达"),
                    basic: .no, premium: .yes),
            PlanRow(icon: "scope", title: L("30 分钟次级别确认"),
                    basic: .no, premium: .yes),
        ]
    }

    // MARK: - 对比表（两档并排，默认路径）

    /// 表格里两个价格/按钮列各自的宽度：够放下「¥188.00/月」和两行中文按钮文案，
    /// 又不至于挤压左边功能名称列（较长的英文文案会换行，属预期内）。
    private static let columnWidth: CGFloat = 96

    /// 两档方案并排的对比表：顶部价格+订阅按钮各占一列（一进付费墙就同时看见两个
    /// 价位，不用先看完高级版一整张卡片再往下滑才发现基础版），下面按行列出功能，
    /// 用勾/横杠标出各自是否包含——比两张纵向长卡片更容易一眼比较。
    private func comparisonTable(basic: Product, premium: Product) -> some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                Text(L("功能")).font(.caption).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                planColumn(basic, planName: L("基础版"), badge: nil)
                    .frame(width: Self.columnWidth)
                planColumn(premium, planName: L("高级版"), badge: L("推荐"))
                    .frame(width: Self.columnWidth)
            }

            Divider().padding(.vertical, 14)

            VStack(spacing: 16) {
                ForEach(planRows) { row in
                    HStack(alignment: .center, spacing: 10) {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: row.icon).foregroundColor(Theme.accent).frame(width: 20)
                            Text(row.title).font(.footnote.bold()).foregroundColor(Theme.textPrimary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        tierCell(row.basic).frame(width: Self.columnWidth)
                        tierCell(row.premium).frame(width: Self.columnWidth)
                    }
                }
            }
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    /// 对比表单元格：包含=实心对勾，不包含=浅色横杠（不用叉号——「基础版没有信号雷达」
    /// 不是缺陷，横杠比红叉更不带负面暗示），有具体额度的直接写数字（如「10 支」）。
    @ViewBuilder
    private func tierCell(_ value: TierValue) -> some View {
        switch value {
        case .yes:
            Image(systemName: "checkmark.circle.fill").foregroundColor(Theme.up)
                .frame(maxWidth: .infinity)
        case .no:
            Image(systemName: "minus.circle").foregroundColor(Theme.textSecondary.opacity(0.35))
                .frame(maxWidth: .infinity)
        case .text(let t):
            Text(t).font(.footnote.bold()).foregroundColor(Theme.textPrimary)
                .frame(maxWidth: .infinity)
        }
    }

    /// 对比表价格列：方案名 + 角标 + 价格 + 订阅按钮，竖直堆叠塞进一列窄栏（Self.columnWidth）。
    /// 有新客资格时显示新客价 + 划线正价（两者都来自 App Store，见 priceRow 注释）。
    private func planColumn(_ product: Product, planName: String, badge: String?) -> some View {
        VStack(spacing: 6) {
            Text(planName).font(.footnote.bold()).foregroundColor(Theme.textPrimary)
            // 没有角标的列也占住同样高度（透明占位），否则只有高级版多一行角标，
            // 两列的价格和订阅按钮上下错开。
            Text(badge ?? L("推荐"))
                .font(.system(size: 9, weight: .bold)).foregroundColor(.white)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Theme.segment, in: Capsule())
                .opacity(badge == nil ? 0 : 1)
                .accessibilityHidden(badge == nil)
            if let trial = store.trialPeriodText(product) {
                Text(L("%@免费试用", trial))
                    .font(.system(size: 11, weight: .bold)).foregroundColor(Theme.up)
                    .multilineTextAlignment(.center)
                Text(L("之后 %@/月", product.displayPrice))
                    .font(.system(size: 9)).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            } else if let intro = store.introDiscount(product) {
                Text(L("新客%@", intro.durationText))
                    .font(.system(size: 10, weight: .bold)).foregroundColor(Theme.segment)
                Text(intro.priceText)
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                    .minimumScaleFactor(0.8).lineLimit(1)
                Text(L("%@/月", product.displayPrice))
                    .strikethrough()
                    .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
            } else {
                Text(L("%@/月", product.displayPrice))
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                    .minimumScaleFactor(0.8).lineLimit(1)
            }
            compactSubscribeButton(product, planName: planName)
        }
    }

    /// 对比表窄列专用的订阅按钮：文案与试用逻辑跟 subscribeButton 完全一致（App
    /// Store 审核要求价格/方案名清楚可见，这里字号更小是为了在窄列里少换行，
    /// 不是省略信息），只是字号更小、允许换行以适应窄列宽度。
    private func compactSubscribeButton(_ product: Product, planName: String) -> some View {
        Button {
            Task { await store.purchase(product) }
        } label: {
            Group {
                if store.purchasingProductID == product.id {
                    ProgressView().tint(.white)
                } else {
                    Text(store.offersFreeTrial(product)
                         ? L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
                         : L("订阅%@", planName))
                        .font(.system(size: 12, weight: .semibold))
                        .multilineTextAlignment(.center)
                }
            }
            .frame(maxWidth: .infinity).padding(.vertical, 10)
            .background(Theme.accent).foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .disabled(store.purchaseInProgress)
        // 另一档正在购买时本按钮置灰（转圈只出现在被点的那个按钮上）
        .opacity(store.purchaseInProgress && store.purchasingProductID != product.id ? 0.45 : 1)
    }

    /// 一张方案卡：权益列表 + 价格 + 订阅按钮。高级版带「推荐」角标。
    private func planCard(
        product: Product, planName: String, badge: String?, rows: [PlanRow]
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
                ForEach(rows) { r in feature(r.icon, r.title) }
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

    private func feature(_ icon: String, _ title: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon).foregroundColor(Theme.accent).frame(width: 24)
            Text(title).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
        }
    }

    /// 划线价只能是真实正价：正价 = product.displayPrice，新客价 = ASC 里配置的推介优惠，
    /// 两者都由 StoreKit 给出，且只对有资格的新客展示。不要在代码里写死「原价」倍数——
    /// 从未按那个价卖过的划线价属于虚构参考价，踩 App Store 2.3.1 / 5.6 与各地价格法。
    private func priceRow(_ product: Product) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                if let trial = store.trialPeriodText(product) {
                    Text(L("%@免费试用", trial)).font(.subheadline.bold()).foregroundColor(Theme.up)
                    Text(L("试用结束后 %@/月，可随时取消", product.displayPrice))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                } else if let intro = store.introDiscount(product) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(intro.priceText).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                        Text(L("%@/月", product.displayPrice))
                            .strikethrough().font(.caption).foregroundColor(Theme.textSecondary)
                    }
                    Text(L("新客专享%@，之后 %@/月，可随时取消", intro.durationText, product.displayPrice))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                } else {
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
                if store.purchasingProductID == product.id { ProgressView().tint(.white) }
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
        // 另一档正在购买时本按钮置灰（转圈只出现在被点的那个按钮上）
        .opacity(store.purchaseInProgress && store.purchasingProductID != product.id ? 0.45 : 1)
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

    /// 当前是否有任一商品带免费试用——目前两档都没配试用期，但披露文案不能写死
    /// 「免费试用结束后」，否则试用期一旦被拿掉（如这次去掉的 3 天试用）文案就说谎；
    /// 以后如果又在 ASC 给某个地区配了试用，也不用记得回来改这行。
    private var anyProductOffersTrial: Bool {
        store.products.contains { store.offersFreeTrial($0) }
    }

    /// 有新客价时的续订披露：写清优惠期多长、之后按什么价续订（3.1.2 要求续订价清楚可见）。
    /// 两档优惠期通常一致，取第一个有优惠的商品的时长。
    private var introDisclosure: String? {
        guard let intro = store.products.lazy.compactMap({ store.introDiscount($0) }).first else { return nil }
        return L("新客专享价仅限首次订阅的 Apple 账户，优惠期（%@）结束后按各方案正价自动续订。", intro.durationText)
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
