import SwiftUI

/// 术语点击后的弹层：先给**当前这只票**该结构的实时数据（最近一笔多长、当前中枢
/// 区间在哪、最近分型什么价……），再接上缠论词条的通用讲解。
///
/// 图例里点「笔 / 线段 / 中枢 / 顶分型 / 底分型」原来只弹一篇跟标的无关的统一教程，
/// 用户看完还是不知道「就这只票现在到底怎样」。这里把实时结构数据摆在讲解前面，
/// 边看自己的票边学概念，比干读定义好记得多。
struct TermInsightView: View {
    let term: String
    let analysis: ChanAnalysis

    @Environment(\.dismiss) private var dismiss

    private var insight: TermInsight? { ChanTermInsight.build(term: term, analysis: analysis) }
    private var article: LessonArticle? { GlossaryIndex.article(for: term) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                dataCard

                if let article = article {
                    Divider().overlay(Theme.border)
                    Text(L("缠论怎么讲"))
                        .font(.footnote.weight(.semibold))
                        .tracking(0.5)
                        .foregroundColor(Theme.textSecondary)
                    LessonArticleContent(article: article)
                }
            }
            .padding(18)
        }
        .background(Theme.background)
        .navigationTitle(L(term))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(L("完成")) { dismiss() }
            }
        }
    }

    // MARK: - 当前数据卡

    @ViewBuilder
    private var dataCard: some View {
        if let insight = insight {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 6) {
                    Image(systemName: "chart.xyaxis.line").foregroundColor(Theme.accent)
                    Text(insight.title).font(.headline).foregroundColor(Theme.textPrimary)
                    Chip(text: L("当前标的"), color: Theme.accent)
                }

                if let headline = insight.headline {
                    Text(headline)
                        .font(.subheadline)
                        .foregroundColor(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 8) {
                    ForEach(insight.rows) { row in
                        HStack(alignment: .top, spacing: 12) {
                            Text(row.label)
                                .font(.footnote)
                                .foregroundColor(Theme.textSecondary)
                            Spacer(minLength: 12)
                            Text(row.value)
                                .font(.footnote.weight(.medium))
                                .foregroundColor(Theme.textPrimary)
                                .multilineTextAlignment(.trailing)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }

                if let note = insight.note {
                    Text(note)
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text(L("本区间还没有成形的%@", L(term)))
                    .font(.subheadline)
                    .foregroundColor(Theme.textPrimary)
                Text(L("换个时间范围、或切到周线看更大级别，可能就有了。"))
                    .font(.footnote)
                    .foregroundColor(Theme.textSecondary)
                    .lineSpacing(3)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }
}

// MARK: - 实时结构数据

/// 单条「标签 : 数值」。
struct TermInsightRow: Identifiable {
    let id = UUID()
    let label: String
    let value: String
}

/// 一个术语在当前标的下的实时数据。
struct TermInsight {
    let title: String
    let headline: String?
    let rows: [TermInsightRow]
    let note: String?
}

/// 把 ChanAnalysis 里该术语相关的结构翻译成可读的实时数据。数据还没成形时返回 nil，
/// 由弹层显示「还没有成形的X」兜底。
enum ChanTermInsight {
    static func build(term: String, analysis: ChanAnalysis) -> TermInsight? {
        switch term {
        case "笔": return stroke(analysis)
        case "线段": return segment(analysis)
        case "中枢": return pivot(analysis)
        case "顶分型": return fractal(analysis, top: true)
        case "底分型": return fractal(analysis, top: false)
        default: return nil
        }
    }

    // MARK: 笔

    private static func stroke(_ a: ChanAnalysis) -> TermInsight? {
        guard let last = a.strokes.last else { return nil }
        let dir = last.direction == .up ? L("上升笔") : L("下降笔")
        let state = last.confirmed ? L("已确认") : L("未确认（最后一笔，可能延伸）")
        return TermInsight(
            title: L("当前的笔"),
            headline: L("最近一笔：%1$@（%2$@）", dir, state),
            rows: [
                TermInsightRow(label: L("笔总数"), value: L("%lld 笔", a.strokes.count)),
                TermInsightRow(label: L("起点"), value: L("%1$@ @ %2$@", last.startTime, fmt(last.startPrice))),
                TermInsightRow(label: L("终点"), value: L("%1$@ @ %2$@", last.endTime, fmt(last.endPrice))),
                TermInsightRow(label: L("幅度"), value: amplitude(last.startPrice, last.endPrice)),
            ],
            note: L("一笔 = 相邻一顶一底之间的连线，是缠论最小的方向单位。")
        )
    }

    // MARK: 线段

    private static func segment(_ a: ChanAnalysis) -> TermInsight? {
        guard let last = a.segments.last else { return nil }
        let dir = last.direction == .up ? L("向上线段") : L("向下线段")
        let state = last.confirmed ? L("已确认") : L("未确认（可能延伸）")
        return TermInsight(
            title: L("当前的线段"),
            headline: L("最近一段：%1$@（%2$@）", dir, state),
            rows: [
                TermInsightRow(label: L("线段总数"), value: L("%lld 段", a.segments.count)),
                TermInsightRow(label: L("构成"), value: L("%lld 笔", last.strokeCount)),
                TermInsightRow(label: L("起点"), value: L("%1$@ @ %2$@", last.startTime, fmt(last.startPrice))),
                TermInsightRow(label: L("终点"), value: L("%1$@ @ %2$@", last.endTime, fmt(last.endPrice))),
                TermInsightRow(label: L("幅度"), value: amplitude(last.startPrice, last.endPrice)),
            ],
            note: L("线段 = 至少 3 笔、方向交替叠出的更大一级方向单位，比单笔更能代表中期趋势。")
        )
    }

    // MARK: 中枢

    private static func pivot(_ a: ChanAnalysis) -> TermInsight? {
        guard let last = a.strokePivots.last ?? a.segmentPivots.last else { return nil }
        let level = last.level == .segment ? L("线段级") : L("笔级")
        let state = last.confirmed ? L("已确认") : L("仍在延伸")
        let strokeCount = a.strokePivots.count
        let segCount = a.segmentPivots.count

        var rows: [TermInsightRow] = [
            TermInsightRow(label: L("中枢总数"),
                           value: L("%1$lld 个（笔级 %2$lld · 线段级 %3$lld）",
                                    strokeCount + segCount, strokeCount, segCount)),
            TermInsightRow(label: L("中枢区间 ZD–ZG"), value: "\(fmt(last.zd))–\(fmt(last.zg))"),
            TermInsightRow(label: L("波动区间 DD–GG"), value: "\(fmt(last.dd))–\(fmt(last.gg))"),
            TermInsightRow(label: L("级别"), value: level),
            TermInsightRow(label: L("状态"), value: state),
        ]
        if let close = a.mergedCandles.last?.close {
            let pos: String
            if close > last.zg {
                pos = L("在中枢上方（多方暂占优）")
            } else if close < last.zd {
                pos = L("跌破中枢下沿（空方暂占优）")
            } else {
                pos = L("在中枢内（多空僵持）")
            }
            rows.append(TermInsightRow(label: L("现价 %@", fmt(close)), value: pos))
        }

        return TermInsight(
            title: L("当前的中枢"),
            headline: nil,
            rows: rows,
            note: L("中枢 = 至少三段走势的重叠区间（ZD–ZG），是多空反复争夺的价格带；现价站在哪一侧，谁就暂时占优。")
        )
    }

    // MARK: 分型

    private static func fractal(_ a: ChanAnalysis, top: Bool) -> TermInsight? {
        let kind: Fractal.Kind = top ? .top : .bottom
        guard let last = a.fractals.last(where: { $0.type == kind }) else { return nil }
        let name = top ? L("顶分型") : L("底分型")
        let state = last.confirmed ? L("已确认") : L("未确认")
        let tops = a.fractals.filter { $0.type == .top }.count
        let bottoms = a.fractals.filter { $0.type == .bottom }.count
        return TermInsight(
            title: L("当前的%@", name),
            headline: L("最近一个%1$@：%2$@ @ %3$@（%4$@）", name, last.time, fmt(last.price), state),
            rows: [
                TermInsightRow(label: L("分型总数"),
                               value: L("%1$lld 个（顶 %2$lld · 底 %3$lld）", a.fractals.count, tops, bottoms)),
            ],
            note: top
                ? L("顶分型 = 中间 K 线的高点比左右两根都高，是一笔向下的起点候选。")
                : L("底分型 = 中间 K 线的低点比左右两根都低，是一笔向上的起点候选。")
        )
    }

    // MARK: 辅助

    private static func fmt(_ v: Double) -> String { String(format: "%.2f", v) }

    /// 起点→终点的涨跌幅度：绝对点数 + 百分比，都带正负号。
    private static func amplitude(_ start: Double, _ end: Double) -> String {
        let diff = end - start
        let pct = start != 0 ? diff / start * 100 : 0
        return L("%1$@ 点（%2$@）",
                 String(format: "%+.2f", diff),
                 String(format: "%+.2f%%", pct))
    }
}
