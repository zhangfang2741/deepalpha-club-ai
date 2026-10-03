import SwiftUI

/// 详情页「分析师评级」分段：评级分布、目标价、业绩预期 vs 实际、最近评级变动。
/// 评级档位是分析师原话，只做引述；我们自己的文字只描述数字。
struct AnalystRatingTab: View {
    let market: StockMarket
    let symbol: String
    @ObservedObject var vm: QuantResearchViewModel

    var body: some View {
        Group {
            switch vm.analyst {
            case .idle, .loading:
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 220)
            case .failed(let message):
                QuantMessageCard(text: message, retry: {
                    Task { await vm.loadAnalyst(market: market, symbol: symbol, force: true) }
                })
            case .loaded(let o):
                if o.isOK {
                    content(o)
                } else {
                    QuantMessageCard(text: o.statusNote ?? L("暂无分析师数据"), footnote: o.note)
                }
            }
        }
        .task { await vm.loadAnalyst(market: market, symbol: symbol) }
    }

    @ViewBuilder
    private func content(_ o: AnalystOverview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let r = o.ratings, let cur = r.current { ratingsCard(cur, r) }
            if let t = o.priceTarget { targetCard(t) }
            if let e = o.earnings, !e.quarters.isEmpty || e.next != nil { earningsCard(e) }
            if !o.recentGrades.isEmpty { gradesCard(o.recentGrades, title: o.recentGradesTitle) }
            Text(o.note).font(.caption2).foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.top, 4)
        }
    }

    // MARK: 评级分布

    private static let buckets: [(String, KeyPath<AnalystOverview.RatingCounts, Int>, Color)] = [
        ("强力买入", \.strongBuy, Theme.up), ("买入", \.buy, Theme.up.opacity(0.6)),
        ("持有", \.hold, Theme.textSecondary.opacity(0.6)), ("卖出", \.sell, Theme.down.opacity(0.6)),
        ("强力卖出", \.strongSell, Theme.down),
    ]

    /// 五档：A 股 / 港股用后端下发的名称（买入 / 增持 / 中性 / 减持 / 卖出，已按语言给出），美股用默认档位。
    static func bucketList(_ labels: [String]?) -> [(String, KeyPath<AnalystOverview.RatingCounts, Int>, Color)] {
        guard let labels, labels.count == buckets.count else {
            return buckets.map { (L($0.0), $0.1, $0.2) }
        }
        return zip(labels, buckets).map { ($0, $1.1, $1.2) }
    }

    private func ratingsCard(_ cur: AnalystOverview.RatingCounts, _ r: AnalystOverview.Ratings) -> some View {
        let buckets = Self.bucketList(r.bucketLabels)
        return card(title: L("评级分布"), trailing: L("%lld 位分析师 · 截至 %@", cur.total, String(cur.date.prefix(7)))) {
            GeometryReader { geo in
                HStack(spacing: 0) {
                    ForEach(buckets, id: \.0) { _, kp, color in
                        Rectangle().fill(color)
                            .frame(width: cur.total > 0 ? geo.size.width * CGFloat(cur[keyPath: kp]) / CGFloat(cur.total) : 0)
                    }
                }
                .clipShape(Capsule())
            }
            .frame(height: 12)
            HStack {
                ForEach(buckets, id: \.0) { name, kp, _ in
                    VStack(spacing: 1) {
                        Text("\(cur[keyPath: kp])").font(.footnote.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                        Text(name).font(.caption2).foregroundStyle(Theme.textSecondary)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            if let text = r.changeText {
                Text(text).font(.caption).foregroundStyle(Theme.textSecondary)
            }
        }
    }

    // MARK: 目标价

    private func targetCard(_ t: AnalystOverview.PriceTarget) -> some View {
        let trailing = t.lastYearCount.map { L("近 12 个月 %lld 次发布", $0) }
        return card(title: L("目标价"), trailing: trailing) {
            if let low = t.low, let high = t.high {
                TargetAxis(price: t.price, low: low, median: t.median, high: high)
            }
            kv(L("现价"), t.price.map { String(format: "%.2f", $0) })
            kv(L("目标价中位数"), t.median.map { String(format: "%.2f", $0) },
               note: t.vsPricePct.map { L("较现价 %@", String(format: "%+.1f%%", $0)) })
            kv(L("目标价区间"), (t.low != nil && t.high != nil) ? String(format: "%.0f ~ %.0f", t.low!, t.high!) : nil)
        }
    }

    // MARK: 业绩

    private func earningsCard(_ e: AnalystOverview.Earnings) -> some View {
        card(title: L("业绩：预期 vs 实际"), trailing: e.next.map { L("下次披露 %@", String($0.date.suffix(5))) }) {
            let maxEps = e.quarters.flatMap { [$0.epsActual, $0.epsEstimated ?? 0] }.map(abs).max() ?? 1
            HStack(alignment: .bottom, spacing: 12) {
                ForEach(e.quarters) { q in
                    VStack(spacing: 3) {
                        HStack(alignment: .bottom, spacing: 3) {
                            bar(q.epsEstimated ?? 0, maxEps, Theme.textSecondary.opacity(0.5))
                            bar(q.epsActual, maxEps, (q.surprisePct ?? 0) >= 0 ? Theme.up : Theme.down)
                        }
                        .frame(height: 50, alignment: .bottom)
                        Text(String(q.date.prefix(7))).font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                        if let s = q.surprisePct {
                            Text(String(format: "%+.1f%%", s)).font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(s >= 0 ? Theme.up : Theme.down)
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            Text(L("灰 = 分析师预期 EPS，彩色 = 实际 EPS；百分比为实际相对预期的差"))
                .font(.caption2).foregroundStyle(Theme.textSecondary)
            if let n = e.next, let eps = n.epsEstimated {
                kv(L("下次披露预期 EPS"), String(format: "%.2f", eps), note: n.date)
            }
        }
    }

    private func bar(_ v: Double, _ maxV: Double, _ color: Color) -> some View {
        RoundedRectangle(cornerRadius: 2).fill(color)
            .frame(width: 10, height: max(3, 50 * CGFloat(abs(v) / max(maxV, 1e-9))))
    }

    // MARK: 最近评级变动

    private func gradesCard(_ grades: [AnalystOverview.GradeChange], title: String?) -> some View {
        card(title: title ?? L("最近评级变动"), trailing: nil) {
            VStack(spacing: 0) {
                ForEach(Array(grades.enumerated()), id: \.element.id) { i, g in
                    if i > 0 { Divider().background(Theme.border) }
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(g.firm).font(.footnote).foregroundStyle(Theme.textPrimary)
                            Text(g.priceTarget.map { L("%@ · 目标价 %@", g.date, String(format: "%.2f", $0)) } ?? g.date)
                                .font(.caption2).foregroundStyle(Theme.textSecondary)
                        }
                        Spacer()
                        Text(g.actionLabel).font(.caption2)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 5))
                            .foregroundStyle(actionColor(g.action))
                        Text(g.previousGradeLabel.map { $0 == g.newGradeLabel ? g.newGradeLabel : "\($0) → \(g.newGradeLabel)" }
                             ?? g.newGradeLabel)
                            .font(.footnote.weight(.medium)).foregroundStyle(Theme.textPrimary)
                    }
                    .padding(.vertical, 7)
                }
            }
        }
    }

    private func actionColor(_ action: String) -> Color {
        switch action {
        case "upgrade": return Theme.up
        case "downgrade": return Theme.down
        default: return Theme.textSecondary
        }
    }

    // MARK: 通用

    private func card<C: View>(title: String, trailing: String?, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                Spacer()
                if let trailing { Text(trailing).font(.caption2).foregroundStyle(Theme.textSecondary) }
            }
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private func kv(_ key: String, _ value: String?, note: String? = nil) -> some View {
        if let value {
            HStack(alignment: .firstTextBaseline) {
                Text(key).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(value).monospacedDigit().foregroundStyle(Theme.textPrimary)
                if let note { Text(note).font(.caption2).foregroundStyle(Theme.textSecondary) }
            }
            .font(.footnote)
        }
    }
}

/// 目标价轴：从 min(现价, 最低) 到 max(现价, 最高)，标现价 / 最低 / 中位 / 最高。
struct TargetAxis: View {
    let price: Double?
    let low: Double
    let median: Double?
    let high: Double

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let lo = min(price ?? low, low)
            let hi = max(price ?? high, high)
            let x: (Double) -> CGFloat = { v in 8 + (w - 16) * CGFloat((v - lo) / max(hi - lo, 1e-9)) }
            ZStack(alignment: .topLeading) {
                Capsule().fill(Theme.surfaceAlt).frame(height: 4).offset(y: 24)
                Capsule().fill(Theme.accent.opacity(0.35))
                    .frame(width: max(x(high) - x(low), 2), height: 8).offset(x: x(low), y: 22)
                tick(x(low), L("最低"), low, Theme.textSecondary, below: true)
                if let median { tick(x(median), L("中位"), median, Theme.accent, below: true) }
                tick(x(high), L("最高"), high, Theme.textSecondary, below: true)
                if let price { tick(x(price), L("现价"), price, Theme.textPrimary, below: false) }
            }
        }
        .frame(height: 64)
    }

    private func tick(_ px: CGFloat, _ name: String, _ v: Double, _ color: Color, below: Bool) -> some View {
        ZStack {
            Rectangle().fill(color).frame(width: 2, height: 18).position(x: px, y: 26)
            VStack(spacing: 0) {
                Text(name).font(.system(size: 10))
                Text(String(format: v >= 100 ? "%.0f" : "%.2f", v)).font(.system(size: 10).monospacedDigit())
            }
            .foregroundStyle(color)
            .fixedSize()
            .position(x: px, y: below ? 52 : 6)
        }
    }
}
