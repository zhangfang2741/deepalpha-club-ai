import SwiftUI

/// 图上可点击的缠论元素。
enum ChartElement: Identifiable, Equatable {
    case fractal(Fractal)
    case stroke(Stroke)
    case segment(Segment)
    case pivot(Pivot)
    case signal(Signal)
    /// 背驰：当前笔与参与比较的前一个同向笔。
    case divergence(current: Stroke, previous: Stroke)

    var id: String {
        switch self {
        case .fractal(let f): return "fx-\(f.id)"
        case .stroke(let s): return "bi-\(s.id)"
        case .segment(let s): return "seg-\(s.id)"
        case .pivot(let p): return "zs-\(p.id)"
        case .signal(let s): return "bs-\(s.id)"
        case .divergence(let c, _): return "div-\(c.id)"
        }
    }

    static func == (a: ChartElement, b: ChartElement) -> Bool { a.id == b.id }
}

/// 点击元素后弹出的简短说明：标题、关键数据、为什么出现在这里、对应课程。
struct ChartExplanation {
    let title: String
    let color: Color
    let facts: [(String, String)]
    let reason: String
    /// 学习模块术语（GlossaryIndex 的中文键），用于跳转课程。
    let lessonTerm: String
}

/// 由图上已有数据拼出言简意赅的说明（不请求后端），方便在真实行情里边看边学。
enum ChartExplainer {
    static func explain(_ element: ChartElement) -> ChartExplanation {
        switch element {
        case .fractal(let f): return fractal(f)
        case .stroke(let s): return stroke(s)
        case .segment(let s): return segment(s)
        case .pivot(let p): return pivot(p)
        case .signal(let s): return signal(s)
        case .divergence(let c, let p): return divergence(c, p)
        }
    }

    static func price(_ v: Double) -> String { String(format: "%.2f", v) }

    static func change(_ from: Double, _ to: Double) -> String {
        guard from != 0 else { return "-" }
        return String(format: "%+.1f%%", (to - from) / from * 100)
    }

    private static func fractal(_ f: Fractal) -> ChartExplanation {
        let top = f.type == .top
        var reason = top
            ? L("这根K线（已做包含处理）的高点高于左右相邻两根，是局部高点：向上笔在这里结束、向下笔从这里开始。")
            : L("这根K线（已做包含处理）的低点低于左右相邻两根，是局部低点：向下笔在这里结束、向上笔从这里开始。")
        if !f.confirmed { reason += L("尚未确认：右侧K线还不够，后续可能被新的极值取代。") }
        return ChartExplanation(
            title: top ? L("顶分型") : L("底分型"),
            color: top ? Theme.topFractal : Theme.bottomFractal,
            facts: [(L("时间"), f.time), (L("价格"), price(f.price))],
            reason: reason, lessonTerm: "分型")
    }

    private static func stroke(_ s: Stroke) -> ChartExplanation {
        let up = s.direction == .up
        var facts: [(String, String)] = [
            (L("起点"), "\(s.startTime)  \(price(s.startPrice))"),
            (L("终点"), "\(s.endTime)  \(price(s.endPrice))"),
            (L("幅度"), change(s.startPrice, s.endPrice)),
        ]
        if let n = s.length { facts.append((L("长度"), L("%lld 根K线", n))) }
        var reason = up
            ? L("从底分型走到顶分型，中间隔着足够多的K线，才算一笔向上笔。笔是缠论里最小的一段走势，买卖点都落在笔的端点上。")
            : L("从顶分型走到底分型，中间隔着足够多的K线，才算一笔向下笔。笔是缠论里最小的一段走势，买卖点都落在笔的端点上。")
        if !s.confirmed { reason += L("这是最后一笔、尚未结束，终点会随新K线移动。") }
        return ChartExplanation(title: up ? L("向上笔") : L("向下笔"), color: Theme.stroke,
                                facts: facts, reason: reason, lessonTerm: "笔")
    }

    private static func segment(_ s: Segment) -> ChartExplanation {
        let up = s.direction == .up
        var reason = L("至少三笔、且前三笔有重叠才构成线段；直到出现反向的特征序列分型（或价格收复线段起点）才结束。线段终点总在段内的最高或最低点。")
        if !s.confirmed { reason += L("这条线段尚未结束，终点还可能延伸。") }
        return ChartExplanation(
            title: up ? L("向上线段") : L("向下线段"), color: Theme.segment,
            facts: [
                (L("起点"), "\(s.startTime)  \(price(s.startPrice))"),
                (L("终点"), "\(s.endTime)  \(price(s.endPrice))"),
                (L("幅度"), change(s.startPrice, s.endPrice)),
                (L("包含"), L("%lld 笔", s.strokeCount)),
            ],
            reason: reason, lessonTerm: "线段")
    }

    private static func pivot(_ p: Pivot) -> ChartExplanation {
        let segLevel = p.level == .segment
        var reason = segLevel
            ? L("连续三条线段的重叠区间：ZG 取各段高点中最低的，ZD 取各段低点中最高的。价格在区间里来回是震荡，离开区间并回抽不回才形成趋势。")
            : L("连续三笔的重叠区间：ZG 取各笔高点中最低的，ZD 取各笔低点中最高的。价格在区间里来回是震荡，离开区间并回抽不回才形成趋势。")
        if !p.confirmed { reason += L("中枢仍在延伸，区间可能继续变化。") }
        return ChartExplanation(
            title: segLevel ? L("线段级中枢") : L("笔级中枢"), color: Theme.pivotFill,
            facts: [
                (L("区间"), "\(price(p.zd)) – \(price(p.zg))"),
                (L("最高 / 最低"), "\(price(p.gg)) / \(price(p.dd))"),
                (L("时间"), "\(p.startTime) → \(p.endTime)"),
            ],
            reason: reason, lessonTerm: "中枢")
    }

    private static func signal(_ s: Signal) -> ChartExplanation {
        var facts: [(String, String)] = [
            (L("时间"), s.time), (L("价格"), price(s.price)),
            (L("强弱"), SignalFormatting.strengthLabel(s.strength)),
            (L("状态"), s.confirmed ? L("已确认") : L("未确认，待后续K线验证")),
        ]
        if let r = s.priceRatio {
            facts.append((L("力度比"), String(format: "%.2f", r)))
        }
        return ChartExplanation(title: s.label, color: s.isBuy ? Theme.up : Theme.down,
                                facts: facts, reason: s.description, lessonTerm: "买卖点")
    }

    private static func divergence(_ c: Stroke, _ p: Stroke) -> ChartExplanation {
        let top = c.direction == .up
        let ratio = c.priceRatio.map { String(format: "%.2f", $0) } ?? "-"
        let reason = top
            ? L("价格创出新高，但这一笔的涨幅只有前一个同向笔的 %@ 倍，量能或时长也更弱——上涨的推动力在衰竭，是趋势可能见顶的信号。", ratio)
            : L("价格创出新低，但这一笔的跌幅只有前一个同向笔的 %@ 倍，量能或时长也更弱——下跌的推动力在衰竭，是趋势可能见底的信号。", ratio)
        return ChartExplanation(
            title: top ? L("顶背驰") : L("底背驰"), color: Theme.divergence,
            facts: [
                (L("本笔"), "\(c.startTime) → \(c.endTime)  \(change(c.startPrice, c.endPrice))"),
                (L("前一同向笔"), "\(p.startTime) → \(p.endTime)  \(change(p.startPrice, p.endPrice))"),
                (L("价差比"), ratio),
            ],
            reason: reason, lessonTerm: "背驰")
    }
}

/// 说明卡片（半屏浮层）：数据 + 原因 + 跳转课程。
struct ChartElementSheet: View {
    let element: ChartElement
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let e = ChartExplainer.explain(element)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(e.facts.enumerated()), id: \.offset) { _, fact in
                            HStack(alignment: .firstTextBaseline) {
                                Text(fact.0)
                                    .font(.footnote)
                                    .foregroundColor(Theme.textSecondary)
                                    .frame(width: 88, alignment: .leading)
                                Text(fact.1)
                                    .font(.footnote.monospacedDigit())
                                    .foregroundColor(Theme.textPrimary)
                                Spacer(minLength: 0)
                            }
                        }
                    }
                    .padding(12)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))

                    Text(e.reason)
                        .font(AnalysisType.body)
                        .foregroundColor(Theme.textPrimary)
                        .lineSpacing(AnalysisType.bodyLineSpacing)
                        .fixedSize(horizontal: false, vertical: true)

                    GlossaryLink(term: e.lessonTerm) {
                        Label(L("学习：") + L(e.lessonTerm), systemImage: "book")
                            .font(AnalysisType.label)
                            .foregroundColor(Theme.accent)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(e.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Circle().fill(e.color).frame(width: 10, height: 10)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
        .presentationDetents([.fraction(0.45), .large])
        .presentationDragIndicator(.visible)
    }
}
