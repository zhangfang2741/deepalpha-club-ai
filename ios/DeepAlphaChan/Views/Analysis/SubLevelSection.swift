import SwiftUI

/// 「次级别确认」卡片：日线定方向 × 30 分钟找买卖点。
///
/// 数据由 ChanViewModel 在日线分析成功后异步加载（不阻塞图表与形态分析）。
/// 周线分析不显示；加载失败或后端未部署该接口时整张卡片不出现，不打扰主结果。
struct SubLevelSection: View {
    @ObservedObject var vm: ChanViewModel

    var body: some View {
        if vm.freq == "daily" {
            if let sub = vm.subLevel {
                card(sub)
            } else if vm.subLevelLoading {
                SectionCard(title: L("次级别确认（30 分钟）"), systemImage: "scope") {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text(L("正在加载 30 分钟级别…"))
                            .font(AnalysisType.body)
                            .foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
    }

    private func card(_ sub: SubLevel) -> some View {
        SectionCard(title: L("次级别确认（30 分钟）"), systemImage: "scope") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text(sub.verdictLabel)
                        .font(AnalysisType.label)
                        .foregroundColor(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Self.verdictColor(sub.verdict)))
                    Text(L("日线：") + sub.dailyBiasLabel)
                        .font(.footnote)
                        .foregroundColor(SignalFormatting.biasColor(sub.dailyBias))
                        .lineLimit(1)
                }

                Text(sub.detail)
                    .font(AnalysisType.body)
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(AnalysisType.bodyLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)

                if !sub.recentSignals.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(L("30 分钟近两日买卖点"))
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                        ForEach(sub.recentSignals) { sig in
                            signalRow(sig)
                        }
                    }
                }

                Button {
                    Task { await vm.switchFreq("30min") }
                } label: {
                    Label(L("查看 30 分钟图表"), systemImage: "chart.xyaxis.line")
                        .font(AnalysisType.label)
                }
                .buttonStyle(.bordered)
                .tint(Theme.accent)
                .disabled(vm.isLoading)

                Text(L("日线定方向、30 分钟找进出点：两者同向为共振，反向多为次级别的反弹或回调。"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func signalRow(_ sig: Signal) -> some View {
        HStack(spacing: 8) {
            Text(sig.label)
                .font(AnalysisType.label)
                .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
            Text(sig.time)
                .font(.footnote.monospacedDigit())
                .foregroundColor(Theme.textSecondary)
            Spacer(minLength: 4)
            Text(String(format: "%.2f", sig.price))
                .font(.footnote.monospacedDigit())
                .foregroundColor(Theme.textPrimary)
            Text(SignalFormatting.strengthLabel(sig.strength))
                .font(.caption)
                .foregroundColor(SignalFormatting.strengthColor(sig.strength))
        }
    }

    /// 共振买=涨色、共振卖=跌色、逆势=橙色警示、等待/不可用=灰。
    static func verdictColor(_ verdict: SubLevel.Verdict) -> Color {
        switch verdict {
        case .resonanceBuy: return Theme.up
        case .resonanceSell: return Theme.down
        case .counterTrend: return Theme.segment
        case .waiting, .unavailable: return Theme.textSecondary
        }
    }
}
