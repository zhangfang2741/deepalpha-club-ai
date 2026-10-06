import SwiftUI

// 「这个结论怎么来的」：所有量化指标统一的推导说明。
// 结论 → 几步推导（每步带这一处、这一天的真实数字）→ 局限。每个指标的文字各自写、不做统一说明页，
// 外壳复用量化研究的 quantExplain 底部弹层。

/// 推导的一步：标题 + 大白话 + 本次的真实数字（可空）。
struct DerivationStep: Identifiable {
    let id = UUID()
    let title: String
    let text: String
    var values: [(String, String)] = []
}

/// 一个指标的完整推导说明：结论 → 这意味着什么 / 不意味着什么 → 几步推导 → 局限 → 相关名词。
/// 面向没学过金融的人：先给结论和「它说明了什么、没说明什么」，再给推导；名词可点开看大白话。
struct DerivationResult {
    let conclusion: String
    var steps: [DerivationStep]
    var caveat: String? = nil
    /// 这个结论说明了什么（大白话）。
    var means: String? = nil
    /// 这个结论不说明什么（避免被误读成预测 / 建议）。
    var notMeans: String? = nil
    /// 相关名词（GlossaryIndex / GlossaryStore 的稳定中文键），显示成可点开的小标签。
    var terms: [String] = []
}

/// 弹层里的内容：结论 → 意味着什么 / 不意味着什么 → 推导步骤 → 局限 → 相关名词。
struct DerivationContent: View {
    let conclusion: String
    let steps: [DerivationStep]
    var caveat: String?
    var means: String?
    var notMeans: String?
    var terms: [String] = []

    init(result: DerivationResult) {
        conclusion = result.conclusion; steps = result.steps; caveat = result.caveat
        means = result.means; notMeans = result.notMeans; terms = result.terms
    }

    init(conclusion: String, steps: [DerivationStep], caveat: String? = nil) {
        self.conclusion = conclusion; self.steps = steps; self.caveat = caveat
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(conclusion)
                .font(QuantTypography.summary).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if means != nil || notMeans != nil {
                VStack(alignment: .leading, spacing: 8) {
                    if let means { meaningRow(icon: "checkmark.circle.fill", color: Theme.accent, title: L("这说明"), text: means) }
                    if let notMeans { meaningRow(icon: "xmark.circle.fill", color: Theme.textSecondary, title: L("这不说明"), text: notMeans) }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
            }
            ForEach(Array(steps.enumerated()), id: \.element.id) { idx, step in
                HStack(alignment: .top, spacing: 10) {
                    Text("\(idx + 1)")
                        .font(.caption.weight(.bold)).foregroundStyle(Theme.accent)
                        .frame(width: 22, height: 22)
                        .background(Theme.accent.opacity(0.14), in: Circle())
                    VStack(alignment: .leading, spacing: 6) {
                        Text(step.title).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                        QuantExplainText(text: step.text, secondary: true)
                        if !step.values.isEmpty {
                            VStack(spacing: 4) {
                                ForEach(Array(step.values.enumerated()), id: \.offset) { _, item in
                                    HStack {
                                        Text(item.0).foregroundStyle(Theme.textSecondary)
                                        Spacer(minLength: 8)
                                        Text(item.1).foregroundStyle(Theme.textPrimary).monospacedDigit()
                                    }
                                    .font(QuantTypography.caption)
                                }
                            }
                            .padding(10)
                            .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
            }
            if let caveat {
                Text(caveat)
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 2)
            }
            if !terms.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L("相关名词")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    WrapLayout(spacing: 8, lineSpacing: 8) {
                        ForEach(terms, id: \.self) { TermChip(term: $0) }
                    }
                }
            }
        }
    }

    private func meaningRow(icon: String, color: Color, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon).font(.system(size: 13)).foregroundStyle(color).padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                QuantExplainText(text: text, secondary: true)
            }
        }
    }
}

/// 一个「怎么算的？」小入口：点开弹出推导。
struct DerivationLink: View {
    let title: String
    let result: DerivationResult
    /// 入口文字；一处有多个入口时（如气泡的深浅 / 共振 / 角标）用它区分。
    var label: String = L("怎么算的")

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "questionmark.circle").font(.system(size: 11))
            Text(label).font(.caption2.weight(.semibold))
        }
        .foregroundStyle(Theme.accent)
        .quantExplain(title) {
            DerivationContent(result: result)
        }
    }
}

/// 数字格式化小工具（推导里的百分比 / 基点 / 点位）。
enum DerivationFormat {
    static func pct(_ v: Double?, digits: Int = 1, signed: Bool = true) -> String {
        guard let v else { return "—" }
        return String(format: signed ? "%+.\(digits)f%%" : "%.\(digits)f%%", v * 100)
    }
    static func num(_ v: Double?, digits: Int = 1) -> String {
        guard let v else { return "—" }
        return String(format: "%.\(digits)f", v)
    }
}

/// 「显示专业数值」开关的存储键（我的页 → 偏好设置）。
enum ProDetails {
    static let key = "show_pro_details"
}
