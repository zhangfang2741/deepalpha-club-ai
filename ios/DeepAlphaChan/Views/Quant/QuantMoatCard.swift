import SwiftUI

/// 护城河卡片（Morningstar 框架）：宽 / 窄 / 无 + 趋势，一句财务证据，五种来源的强弱点阵。
/// 点哪儿解释哪儿：评级 → 怎么评出来的；证据 → 历年回报率对比资金成本；每种来源 → 理由 + 年报原文。
struct QuantMoatCard: View {
    let moat: QuantMoat
    var isStatic = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if moat.isOK {
                if let ev = moat.evidence {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(ev.text).font(QuantTypography.body).foregroundStyle(Theme.textPrimary.opacity(0.9))
                            .fixedSize(horizontal: false, vertical: true)
                        if !isStatic { QuantInfoMark() }
                    }
                    .quantExplain(L("财务证据：回报率是否长期高于资金成本"), enabled: !isStatic) {
                        QuantMoatEvidenceExplanation(evidence: ev)
                    }
                }
                VStack(spacing: 0) {
                    ForEach(Array(moat.sources.enumerated()), id: \.element.id) { i, s in
                        if i > 0 { Divider().overlay(Theme.border) }
                        sourceRow(s)
                    }
                }
                .padding(.horizontal, 10)
                .background(Theme.surfaceAlt.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
                if let threats = moat.threats, !threats.isEmpty {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "exclamationmark.triangle").font(QuantTypography.metadata)
                            .foregroundStyle(Theme.segment).padding(.top, 2).accessibilityHidden(true)
                        Text(L("主要威胁：") + threats).font(QuantTypography.metadata)
                            .foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
            } else if let note = moat.statusNote {
                Text(note).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            footer
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: "shield.lefthalf.filled").font(QuantTypography.title)
                .foregroundStyle(QuantMoatStyle.color(moat.rating)).accessibilityHidden(true)
            Text(L("护城河")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
            Spacer(minLength: 6)
            if let name = moat.ratingName {
                Text(name)
                    .font(QuantTypography.emphasis).foregroundStyle(QuantMoatStyle.color(moat.rating))
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(QuantMoatStyle.color(moat.rating).opacity(0.14), in: Capsule())
                    .quantExplain(L("护城河评级怎么来的"), enabled: !isStatic) {
                        QuantMoatRatingExplanation(moat: moat)
                    }
            } else {
                Text(moat.status == "pending" ? L("评估中") : L("暂未覆盖"))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
            if let trend = moat.trendName {
                Label(trend, systemImage: QuantMoatStyle.trendIcon(moat.trend))
                    .labelStyle(.iconOnly).font(QuantTypography.metadata)
                    .foregroundStyle(QuantMoatStyle.trendColor(moat.trend))
                    .accessibilityLabel(trend)
            }
        }
    }

    private func sourceRow(_ s: QuantMoatSource) -> some View {
        HStack(spacing: 10) {
            Text(s.name).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
            Spacer(minLength: 6)
            QuantMoatDots(filled: s.dots)
            Text(s.strengthName).font(QuantTypography.metadata)
                .foregroundStyle(s.dots >= 2 ? Theme.textPrimary : Theme.textSecondary)
                .frame(minWidth: 18, alignment: .trailing)
            if !isStatic {
                Image(systemName: "chevron.right").font(.system(size: 10)).foregroundStyle(Theme.textSecondary)
                    .accessibilityHidden(true)
            }
        }
        .padding(.vertical, 9)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .quantExplain(s.name + " · " + s.strengthName, enabled: !isStatic) {
            QuantMoatSourceExplanation(source: s, filedDate: moat.filedDate)
        }
    }

    private var footer: some View {
        HStack(spacing: 4) {
            Text(moat.filedDate.map { L("只展示，不计入综合等级 · 依据 %@ 年报", $0) } ?? L("只展示，不计入综合等级"))
                .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            if !isStatic { QuantInfoMark() }
        }
        .quantExplain(L("护城河是怎么评的"), enabled: !isStatic) {
            QuantExplainText(text: moat.methodNote)
        }
    }
}

enum QuantMoatStyle {
    /// 沿用 App 红强绿弱：宽 = 红、窄 = 浅红、无 = 灰。
    static func color(_ rating: String?) -> Color {
        switch rating {
        case "wide": return Theme.up
        case "narrow": return Theme.up.opacity(0.7)
        default: return Theme.textSecondary
        }
    }

    static func trendIcon(_ trend: String?) -> String {
        switch trend {
        case "widening": return "arrow.up.right"
        case "narrowing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    static func trendColor(_ trend: String?) -> Color {
        switch trend {
        case "widening": return Theme.up
        case "narrowing": return Theme.down
        default: return Theme.textSecondary
        }
    }
}

/// 强度点阵：●●● 强、●●○ 中、●○○ 弱、○○○ 无。
struct QuantMoatDots: View {
    let filled: Int

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<3, id: \.self) { i in
                Circle().fill(i < filled ? Theme.up.opacity(0.85) : Theme.border).frame(width: 7, height: 7)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - 解释气泡

/// 评级：证据与来源同时成立才算有护城河。
struct QuantMoatRatingExplanation: View {
    let moat: QuantMoat

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            QuantExplainText(text: L("和 Morningstar 一样分三档：宽护城河 = 优势大概率能维持 20 年以上；窄护城河 = 大概率能维持 10 年以上；无护城河 = 利润容易被竞争拉低。"))
            if let ev = moat.evidence {
                QuantExplainText(text: L("① 财务证据（%@）：", ev.levelName) + ev.text)
            }
            if let summary = moat.summary {
                QuantExplainText(text: L("② 年报里的来源：") + summary)
            }
            QuantExplainText(text: L("宽 = 财务证据强 + 至少 1 个强来源（或 2 个中等来源）；窄 = 财务证据至少一般 + 至少 1 个中等以上来源；否则为无。来源再强，财务上长期跑不赢资金成本也不算有护城河。"),
                             secondary: true)
            if let trend = moat.trendName {
                QuantExplainText(text: L("趋势「%@」：比较最近 3 年和最早 3 年的平均超额回报，相差超过 2 个百分点才算扩大或收窄。", trend),
                                 secondary: true)
            }
        }
    }
}

/// 财务证据：历年回报率柱状 + 资金成本线。
struct QuantMoatEvidenceExplanation: View {
    let evidence: QuantMoatEvidence

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            QuantExplainText(text: evidence.metric == "roe"
                ? L("银行、保险等金融公司的投入资本口径不可比，这里用 ROE（股东每投入 100 元一年赚回多少）对比股权资金成本。")
                : L("ROIC = 投进生意里的每 100 元一年赚回多少。只有长期高于资金成本（借钱和股东要求的回报），公司才是在创造价值。"))
            chart
            QuantExplainText(text: L("资金成本约 %@：按无风险利率 4.3%% + β × 股权风险溢价 5%% 估算（再与税后债务成本按市值 / 负债加权）。",
                                     String(format: "%.1f%%", evidence.costOfCapital * 100)), secondary: true)
            QuantExplainText(text: L("财务证据强 = 至少 8 年数据、最多 1 年没跑赢、平均高出 3 个百分点以上；一般 = 至少 5 年、七成年份跑赢且平均为正。"),
                             secondary: true)
        }
    }

    private var chart: some View {
        let ys = Array(evidence.years.reversed())   // 旧 → 新
        let maxV = max(ys.map(\.value).max() ?? 0, evidence.costOfCapital) * 1.15
        let minV = min(ys.map(\.value).min() ?? 0, 0)
        let span = max(maxV - minV, 1e-6)
        return VStack(alignment: .leading, spacing: 4) {
            GeometryReader { geo in
                let h = geo.size.height
                let y: (Double) -> CGFloat = { v in h * CGFloat((maxV - v) / span) }
                ZStack(alignment: .topLeading) {
                    HStack(alignment: .bottom, spacing: 4) {
                        ForEach(ys) { p in
                            let top = y(max(p.value, 0)), bottom = y(min(p.value, 0))
                            VStack(spacing: 0) {
                                Spacer(minLength: 0).frame(height: top)
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(p.value > evidence.costOfCapital ? Theme.up.opacity(0.8) : Theme.down.opacity(0.8))
                                    .frame(height: max(bottom - top, 1))
                                Spacer(minLength: 0)
                            }
                            .frame(maxWidth: .infinity)
                        }
                    }
                    Rectangle().fill(Theme.textPrimary.opacity(0.7)).frame(height: 1)
                        .offset(y: y(evidence.costOfCapital))
                }
            }
            .frame(height: 90)
            HStack {
                Text(ys.first.map { String($0.year) } ?? "")
                Spacer()
                Text(L("白线 = 资金成本")).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(ys.last.map { String($0.year) } ?? "")
            }
            .font(.system(size: 9).monospacedDigit()).foregroundStyle(Theme.textSecondary)
        }
        .accessibilityHidden(true)
    }
}

/// 一种来源：大白话理由 + 年报原文（逐字核对过）。
struct QuantMoatSourceExplanation: View {
    let source: QuantMoatSource
    let filedDate: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            QuantExplainText(text: QuantMoatSourceGuide.meaning(source.key), secondary: true)
            QuantExplainText(text: source.reason)
            if source.dots > 0, !source.quotes.isEmpty {
                Text(filedDate.map { L("年报原文（%@ 10-K）", $0) } ?? L("年报原文"))
                    .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                ForEach(source.quotes, id: \.self) { q in
                    Text("“\(q)”").font(QuantTypography.metadata.italic())
                        .foregroundStyle(Theme.textPrimary.opacity(0.85))
                        .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 8))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

/// 五种来源各是什么意思（一句话）。
enum QuantMoatSourceGuide {
    static func meaning(_ key: String) -> String {
        switch key {
        case "intangible_assets": return L("无形资产：让客户愿意多付钱、或让对手进不来的品牌、专利、牌照。")
        case "switching_costs": return L("转换成本：客户想换掉它，要付出很多钱、时间或风险。")
        case "network_effect": return L("网络效应：用的人越多，对每个用户越有价值，比如支付网络、交易平台。")
        case "cost_advantage": return L("成本优势：能比对手更便宜地做出同样的东西，而且长期如此。")
        case "efficient_scale": return L("有效规模：市场只容得下少数几家，新来的进来大家都不赚钱，比如管道、机场。")
        default: return ""
        }
    }
}
