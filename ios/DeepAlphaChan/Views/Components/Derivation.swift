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

/// 弹层里的内容：结论 → 推导步骤 → 局限。
struct DerivationContent: View {
    let conclusion: String
    let steps: [DerivationStep]
    var caveat: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(conclusion)
                .font(QuantTypography.summary).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
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
        }
    }
}

/// 一个「怎么算的？」小入口：点开弹出推导。
struct DerivationLink: View {
    let title: String
    let conclusion: String
    let steps: [DerivationStep]
    var caveat: String?

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "questionmark.circle").font(.system(size: 11))
            Text(L("怎么算的")).font(.caption2.weight(.semibold))
        }
        .foregroundStyle(Theme.accent)
        .quantExplain(title) {
            DerivationContent(conclusion: conclusion, steps: steps, caveat: caveat)
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
