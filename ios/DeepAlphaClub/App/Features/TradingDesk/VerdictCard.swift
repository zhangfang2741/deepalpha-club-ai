import SwiftUI
import DeepAlphaCore

/// 裁决卡：动作 + 置信度 + 仓位/止损/目标价/周期 2×2 + 降级警告 + 理由 + 审计链。
struct VerdictCard: View {
    let verdict: VerdictData?
    let turns: [Turn]
    @State private var auditOpen = false

    private var confPct: Int? {
        verdict.map { Int(($0.confidence * 100).rounded()) }
    }

    /// 价格保留两位，避免 String(150.0) 直出 "150.0"。
    private func price(_ v: Double?) -> String? {
        v.map { String(format: "%.2f", $0) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(verdict?.signal.label ?? "—")
                    .font(.title2.weight(.heavy))
                    .foregroundStyle(verdict?.signal.tint ?? Color.secondary)
                Spacer()
                Text("置信度")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                Text(confPct.map { "\($0)%" } ?? "—")
                    .font(.callout.monospaced().weight(.semibold))
            }

            Grid(horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    field("仓位", verdict.map { String(format: "%.1f%%", $0.sizeFraction * 100) })
                    field("止损", price(verdict?.stopLoss))
                }
                GridRow {
                    field("目标价", price(verdict?.targetPrice))
                    field("周期", verdict?.timeHorizonDays.map { "\($0) 天" })
                }
            }

            // 引擎降级解析警告：必须显式展示，否则用户把降级结论当正常结论
            if let warning = verdict?.warningMessage {
                Label {
                    Text("结论解析降级：\(warning)").font(.footnote)
                } icon: {
                    Image(systemName: "exclamationmark.triangle.fill")
                }
                .foregroundStyle(.orange)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
            }

            if let rationale = verdict?.rationale, !rationale.isEmpty {
                Text(rationale)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
            }

            let audit = TradingDeskReducer.buildAuditChain(turns)
            if !audit.isEmpty {
                DisclosureGroup(isExpanded: $auditOpen) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(audit.enumerated()), id: \.offset) { i, entry in
                            Text("\(entry.who) —— \(entry.excerpt)")
                                .font(.caption2)
                                .foregroundStyle(entry.human ? .blue : .secondary)
                                .lineLimit(2)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            if i < audit.count - 1 { Divider() }
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    Text("审计链（\(audit.count) 步）")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.blue)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.tertiarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 12))
        .opacity(verdict == nil ? 0.6 : 1)
    }

    private func field(_ label: String, _ value: String?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption2).foregroundStyle(.tertiary)
            Text(value ?? "—")
                .font(.callout.monospaced().weight(.semibold))
                .foregroundStyle(value == nil ? Color.secondary : Color.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
