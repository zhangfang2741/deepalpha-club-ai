import SwiftUI

/// 分段控件的「买卖点」段：逐条列出识别到的买卖点。
///
/// 每条的类型标签（一买、二买……）和「面积比」都接了术语跳转——这几个词
/// 恰恰是新手最容易看不懂、又最影响判断的。
struct SignalListSection: View {
    let analysis: ChanAnalysis

    /// 按时间倒序（最新在最上）。后端返回的顺序不保证有序；而用户翻到这一段
    /// 最想先看「最近发生了什么」，最新信号不该被压在长列表的底部。
    private var sortedSignals: [Signal] {
        analysis.signals.sorted { $0.time > $1.time }
    }

    var body: some View {
        VStack(spacing: 12) {
            SectionCard(title: L("买卖点"), systemImage: "flag.fill") {
                if analysis.signals.isEmpty {
                    emptyHint
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        // 常驻说明：明确「买卖点」是缠论的技术信号名词，不是操作指令
                        Text(L("「买卖点」是缠论对价格结构的技术信号命名，非买入/卖出操作建议。"))
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        ForEach(sortedSignals) { sig in signalRow(sig) }
                    }
                }
            }

            disclaimer
        }
    }

    private var emptyHint: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("当前区间未识别到明确买卖点"))
                .font(AnalysisType.body).foregroundColor(Theme.textPrimary)
            Text(L("可以试试换个时间范围，或切到周线看更大级别的结构。"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .lineSpacing(3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func signalRow(_ sig: Signal) -> some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 3)
                .fill(sig.isBuy ? Theme.up : Theme.down)
                .frame(width: 4)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    // 「一买」「二卖」这类标签直接接词条。不加下划线：中文小字号下
                    // 虚下划线贴着字身，看起来像删除线；这里靠尾随的问号图标提示可点。
                    GlossaryLink(term: sig.label) {
                        HStack(spacing: 2) {
                            Text(sig.label)
                                .font(.subheadline.bold())
                                .foregroundColor(sig.isBuy ? Theme.up : Theme.down)
                            if GlossaryIndex.hasEntry(for: sig.label) {
                                Image(systemName: "questionmark.circle")
                                    .font(.system(size: 10))
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                    }
                    Chip(text: SignalFormatting.strengthLabel(sig.strength),
                         color: SignalFormatting.strengthColor(sig.strength))
                    if !sig.confirmed { Chip(text: L("未确认"), color: Theme.textSecondary) }
                    Spacer()
                    Text(sig.time).font(.caption).foregroundColor(Theme.textSecondary)
                }
                // 与形态分析段同一套字号，两段来回切时不该有字号跳变
                Text(sig.description)
                    .font(AnalysisType.body)
                    .foregroundColor(Theme.textSecondary)
                    .lineSpacing(AnalysisType.bodyLineSpacing)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 12) {
                    Text(L("价位 %@", String(format: "%.2f", sig.price)))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                    if let ar = sig.areaRatio {
                        GlossaryLink(term: "面积比") {
                            HStack(spacing: 2) {
                                Text(L("面积比 %@", String(format: "%.2f", ar)))
                                    .font(.caption2)
                                    .foregroundColor(Theme.textSecondary)
                                Image(systemName: "questionmark.circle")
                                    .font(.system(size: 9))
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                    }
                }
            }
        }
        .padding(10)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    /// 买卖点是这个 App 里最像「投资建议」的部分，提示放在这一段而不是全局，
    /// 出现在用户真正会误读的地方。
    private var disclaimer: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "info.circle")
                .font(.caption2).foregroundColor(Theme.textSecondary)
            Text(L("以上为结构识别结果，不构成投资建议。信号需与你的持仓周期匹配，参见学习页「走势级别」。"))
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        // 补回卡片那一层内边距，脚注才和卡片里的文字左对齐
        .padding(.horizontal, 8)
    }
}
