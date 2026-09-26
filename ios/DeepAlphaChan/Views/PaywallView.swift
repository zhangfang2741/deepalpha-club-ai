import SwiftUI
import StoreKit

/// 方案卡上的一条权益（单卡展示用，仅在只加载到一个商品的兜底路径里使用）。
private struct PlanFeature: Identifiable {
    let icon: String
    let title: String
    let desc: String
    var id: String { title }
}

/// 对比表里的一行权益：同一行，标出基础版/高级版各自是否包含。
private struct ComparisonFeature: Identifiable {
    let icon: String
    let title: String
    let inBasic: Bool
    let inPremium: Bool
    var id: String { title }
}

/// 订阅付费墙。展示两档方案（基础版 / 高级版）的权益、价格与免费试用，
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
            Text(L("解锁全部缠论分析，突破每日 %lld 次限制", AppConfig.freeDailyQuota))
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
            planCard(
                product: only,
                planName: only.id == AppConfig.premiumMonthlyProductID ? L("高级版") : L("基础版"),
                badge: only.id == AppConfig.premiumMonthlyProductID ? L("推荐") : nil,
                features: only.id == AppConfig.premiumMonthlyProductID ? premiumFeatures : basicFeatures)
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

    // MARK: - 兜底：只加载到一个商品时的单卡展示（详见 content 里的 else if let only 分支）

    private var premiumFeatures: [PlanFeature] {
        [
            PlanFeature(icon: "infinity", title: L("无限次缠论分析"), desc: L("不再受每日次数限制")),
            PlanFeature(icon: "scope", title: L("30 分钟次级别确认"),
                        desc: L("日线定方向、30 分钟找进出点，共振/逆势一眼分辨")),
            PlanFeature(icon: "dot.radiowaves.left.and.right", title: L("信号雷达"),
                        desc: L("扫描科技指数成分股，每日买卖点一图看全")),
            PlanFeature(icon: "star.fill", title: L("自选批量状态计算"),
                        desc: L("自选列表批量算出每只标的当前所处的结构阶段")),
            PlanFeature(icon: "globe.asia.australia.fill", title: L("美股 / A 股 / 港股"),
                        desc: L("三个市场统一的缠论结构分析")),
        ]
    }

    private var basicFeatures: [PlanFeature] {
        [
            PlanFeature(icon: "infinity", title: L("无限次缠论分析"), desc: L("不再受每日次数限制")),
            PlanFeature(icon: "globe.asia.australia.fill", title: L("美股 / A 股 / 港股"),
                        desc: L("三个市场统一的缠论结构分析")),
            // 不写「操作倾向」：付费墙是宣传语境，这四个字等于在卖操作建议，
            // 正踩 3.1.1 / 5.2.5。口径与 App 内的「形态分析」保持一致。
            PlanFeature(icon: "flag.fill", title: L("全部买卖点与形态分析"),
                        desc: L("一二三类买卖点、背驰与加权依据")),
        ]
    }

    // MARK: - 对比表（两档并排，默认路径）

    /// 表格里两个价格/按钮列各自的宽度：够放下「¥188.00/月」和两行中文按钮文案，
    /// 又不至于挤压左边功能名称列（较长的英文文案会换行，属预期内）。
    private static let columnWidth: CGFloat = 96

    private var comparisonFeatures: [ComparisonFeature] {
        [
            .init(icon: "infinity", title: L("无限次缠论分析"), inBasic: true, inPremium: true),
            .init(icon: "scope", title: L("30 分钟次级别确认"), inBasic: false, inPremium: true),
            .init(icon: "flag.fill", title: L("全部买卖点与形态分析"), inBasic: true, inPremium: true),
            .init(icon: "globe.asia.australia.fill", title: L("美股 / A 股 / 港股"), inBasic: true, inPremium: true),
            .init(icon: "dot.radiowaves.left.and.right", title: L("信号雷达"), inBasic: false, inPremium: true),
            .init(icon: "star.fill", title: L("自选批量状态计算"), inBasic: false, inPremium: true),
        ]
    }

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
                ForEach(comparisonFeatures) { row in
                    HStack(alignment: .top, spacing: 10) {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: row.icon).foregroundColor(Theme.accent).frame(width: 20)
                            Text(row.title).font(.footnote).foregroundColor(Theme.textPrimary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        checkMark(row.inBasic).frame(width: Self.columnWidth)
                        checkMark(row.inPremium).frame(width: Self.columnWidth)
                    }
                }
            }
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.border, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    /// 对比表功能行里的勾选标记：包含=实心对勾（强调色），不包含=浅色横杠
    /// （不用叉号——「基础版没有信号雷达」不是缺陷，用横杠比红叉更不带负面暗示）。
    private func checkMark(_ included: Bool) -> some View {
        Image(systemName: included ? "checkmark.circle.fill" : "minus.circle")
            .foregroundColor(included ? Theme.up : Theme.textSecondary.opacity(0.35))
            .frame(maxWidth: .infinity)
    }

    /// 对比表价格列：方案名 + 角标 + 真实价格（不做划线原价，见 priceRow）+ 订阅按钮，
    /// 竖直堆叠塞进一列窄栏（Self.columnWidth）。
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
                if store.purchaseInProgress {
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

    /// 价格只显示 App Store 的真实扣款价，不做「划线原价 / 限时活动价」对比：
    /// 从未按那个原价卖过，属于虚构参考价，踩 App Store 2.3.1 / 5.6（误导性营销）
    /// 与各地价格法。以后真要做限时折扣，用 ASC 的推介/促销优惠，价格由 StoreKit 给出。
    private func priceRow(_ product: Product) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                if let trial = store.trialPeriodText(product) {
                    Text(L("%@免费试用", trial)).font(.subheadline.bold()).foregroundColor(Theme.up)
                    Text(L("试用结束后 %@/月，可随时取消", product.displayPrice))
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

    /// 当前是否有任一商品带免费试用——目前两档都没配试用期，但披露文案不能写死
    /// 「免费试用结束后」，否则试用期一旦被拿掉（如这次去掉的 3 天试用）文案就说谎；
    /// 以后如果又在 ASC 给某个地区配了试用，也不用记得回来改这行。
    private var anyProductOffersTrial: Bool {
        store.products.contains { store.offersFreeTrial($0) }
    }

    /// 自动续订披露 + 条款/隐私链接（App Store 审核必备）。
    private var legal: some View {
        VStack(spacing: 8) {
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
