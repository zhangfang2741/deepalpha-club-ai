import SwiftUI
import StoreKit

/// 付费墙的一行权益：只列订阅后才有的——免费版也能用的（买卖点与形态分析、三个市场）不列，
/// 否则等于把免费功能包装成付费权益（2.3.1，也会让用户觉得被误导）。
/// `value` 有值时右侧写具体额度（如「不限」），没有就是普通勾选项。
private struct PlanRow: Identifiable {
    let group: String
    let icon: String
    let title: String
    var value: String? = nil
    var id: String { title }
}

/// 订阅付费墙。只有一个会员（2026-10-05 起，原基础版 / 高级版合并）：一张卡片列出全部权益、价格，
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
            // tier 变化（购买/恢复成功）即关闭
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
            Text(L("不限次分析 · 市场雷达 · 次级别确认"))
                .font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 8)
    }

    @ViewBuilder
    private var content: some View {
        if let product = store.membershipProduct {
            membershipCard(product)
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
    /// - 分析次数：免费每日 AppConfig.freeDailyQuota 支不同标的（UsageTracker），会员不限
    /// - 自选上限：免费 1 / 会员不限（后端 app/services/watchlist.py TIER_LIMITS）
    /// - 自选结构状态：免费只显示最早加入的 1 支，会员全部（WatchlistViewModel.phase(for:)）
    /// - 信号雷达：会员可看每日真实雷达（含近 30 个交易日历史回看），免费只有示例日
    /// - 次级别确认（日线×30 分钟、周线×日线）：会员专属（MainTabView.hasSubLevelAccess）
    /// 文案只描述功能本身，不暗示收益或操作建议（3.1.1 / 5.2.5）。
    private var planRows: [PlanRow] {
        let analysis = L("缠论分析"), watchlist = L("自选股"), radar = L("市场雷达")
        return [
            PlanRow(group: analysis, icon: "infinity", title: L("分析次数"), value: L("不限")),
            PlanRow(group: analysis, icon: "scope", title: L("30 分钟次级别")),
            PlanRow(group: analysis, icon: "calendar", title: L("周线看日线")),
            PlanRow(group: watchlist, icon: "star.fill", title: L("自选数量"), value: L("不限")),
            PlanRow(group: watchlist, icon: "square.stack.3d.up.fill", title: L("自选状态"), value: L("全部")),
            PlanRow(group: radar, icon: "dot.radiowaves.left.and.right", title: L("每日雷达")),
            PlanRow(group: radar, icon: "clock.arrow.circlepath", title: L("历史回看")),
        ]
    }

    /// 按分组保持顺序（缠论分析 → 自选股 → 信号雷达）。
    private var groupedPlanRows: [(group: String, rows: [PlanRow])] {
        var out: [(group: String, rows: [PlanRow])] = []
        for row in planRows {
            if let i = out.firstIndex(where: { $0.group == row.group }) {
                out[i].rows.append(row)
            } else {
                out.append((row.group, [row]))
            }
        }
        return out
    }

    // MARK: - 会员卡

    /// 一张卡：全部权益 + 价格 + 订阅按钮。
    private func membershipCard(_ product: Product) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 18) {
                ForEach(groupedPlanRows, id: \.group) { section in
                    VStack(alignment: .leading, spacing: 12) {
                        Text(section.group)
                            .font(.caption.bold()).foregroundColor(Theme.textSecondary)
                        ForEach(section.rows) { row in
                            HStack(spacing: 10) {
                                Image(systemName: row.icon).foregroundColor(Theme.accent).frame(width: 24)
                                Text(row.title).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                                Spacer(minLength: 8)
                                if let value = row.value {
                                    Text(value).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                                } else {
                                    Image(systemName: "checkmark.circle.fill").foregroundColor(Theme.accent)
                                }
                            }
                        }
                    }
                }
            }
            priceRow(product)
            subscribeButton(product)
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.segment.opacity(0.5), lineWidth: 1.5))
        .clipShape(RoundedRectangle(cornerRadius: 14))
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

    private func subscribeButton(_ product: Product) -> some View {
        Button {
            Task { await store.purchase(product) }
        } label: {
            HStack {
                if store.purchasingProductID == product.id { ProgressView().tint(.white) }
                Text(store.offersFreeTrial(product)
                     ? L("开始 %@免费试用", store.trialPeriodText(product) ?? "")
                     : L("订阅%@", L("会员")))
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
