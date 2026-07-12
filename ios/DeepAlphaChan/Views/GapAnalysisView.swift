import SwiftUI

/// 市场结构 × 产业结构 GAP 分析（异步 LLM 任务）。
struct GapAnalysisView: View {
    @ObservedObject var vm: ChanViewModel

    var body: some View {
        SectionCard(title: "结构 GAP 分析", systemImage: "arrow.triangle.branch") {
            VStack(alignment: .leading, spacing: 12) {
                Text("填写你对该标的的产业结构判断（基本面观点），系统会对比技术面结构，找出背离点。")
                    .font(.caption).foregroundColor(Theme.textSecondary)

                TextEditor(text: $vm.industryView)
                    .frame(height: 90)
                    .padding(8)
                    .scrollContentBackground(.hidden)
                    .background(Theme.surfaceAlt)
                    .foregroundColor(Theme.textPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(alignment: .topLeading) {
                        if vm.industryView.isEmpty {
                            Text("例如：AI 需求强劲，公司在数据中心 GPU 供应链居核心，产能持续扩张……")
                                .font(.caption).foregroundColor(Theme.textSecondary.opacity(0.6))
                                .padding(14).allowsHitTesting(false)
                        }
                    }

                Button {
                    Task { await vm.runGapAnalysis() }
                } label: {
                    HStack {
                        if vm.gapLoading { ProgressView().tint(.white) }
                        Text(vm.gapLoading ? "分析中（约需 10–60 秒）…" : "开始 GAP 分析")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, 12)
                    .background(Theme.accent).foregroundColor(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .disabled(vm.gapLoading)

                if let error = vm.gapError {
                    Text(error).font(.footnote).foregroundColor(Theme.down)
                }

                if let result = vm.gapResult { resultView(result) }
            }
        }
    }

    private func resultView(_ r: StructureGapResult) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider().background(Theme.border)

            if !r.gaps.isEmpty {
                Text("背离点（重点）").font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                ForEach(r.gaps) { gap in gapItemView(gap) }
            }

            if !r.aligned.isEmpty {
                Text("已一致处（多已定价）").font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                ForEach(r.aligned, id: \.self) { a in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "checkmark.circle.fill").font(.caption).foregroundColor(Theme.up)
                        Text(a).font(.caption).foregroundColor(Theme.textSecondary)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("最值得研究的问题").font(.caption.bold()).foregroundColor(Theme.accent)
                Text(r.keyQuestion).font(.subheadline).foregroundColor(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(10).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.accent.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 8))

            if !r.caveats.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(r.caveats, id: \.self) { c in
                        Text("• \(c)").font(.caption2).foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
    }

    private func gapItemView(_ gap: GapItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(gap.dimension).font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
                Spacer()
                Chip(text: directionLabel(gap.direction), color: directionColor(gap.direction))
            }
            HStack(alignment: .top, spacing: 12) {
                labeled("技术面", gap.marketSays)
                labeled("产业面", gap.industrySays)
            }
            Text(gap.interpretation).font(.caption).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10).background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func labeled(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption2.bold()).foregroundColor(Theme.textSecondary)
            Text(value).font(.caption).foregroundColor(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func directionLabel(_ d: GapItem.Direction) -> String {
        switch d {
        case .priceLagsIndustry: return "价格滞后产业"
        case .priceAheadOfFundamentals: return "价格领先基本面"
        case .unclear: return "尚不明确"
        }
    }
    private func directionColor(_ d: GapItem.Direction) -> Color {
        switch d {
        case .priceLagsIndustry: return Theme.up
        case .priceAheadOfFundamentals: return Theme.down
        case .unclear: return Theme.textSecondary
        }
    }
}
