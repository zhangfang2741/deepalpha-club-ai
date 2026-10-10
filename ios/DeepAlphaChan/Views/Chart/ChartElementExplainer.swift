import SwiftUI

/// 图上可点击的缠论元素。
enum ChartElement: Identifiable, Equatable {
    case fractal(Fractal)
    case stroke(Stroke)
    case segment(Segment)
    case pivot(Pivot)
    case signal(Signal)
    /// 买卖点的成立日标记（徽标向右的虚线终点的圆点）：与徽标同一个信号，点它解释「为什么成立日比徽标晚」。
    case established(Signal)
    /// 背驰：c 段终点所在的笔 + 参照点（b 段终点；旧后端是前一个同向笔的终点）。
    case divergence(current: Stroke, refTime: String, refPrice: Double)
    /// 威科夫事件标记（指标栏打开「威科夫」后图上的 SC / Spring / SOS 等）。
    case wyckoff(WyckoffEventMark)
    /// SMC 指标里的元素（结构突破 / 订单块 / 缺口 / 等高低点 / 扫荡 / 溢价折价 / 强弱高低点 / 前周期高低点）。
    /// `swingLen` 是后端识别摆动点用的长度，说明文字里要写出来。
    case smc(SmcMark, swingLen: Int)

    var id: String {
        switch self {
        case .fractal(let f): return "fx-\(f.id)"
        case .stroke(let s): return "bi-\(s.id)"
        case .segment(let s): return "seg-\(s.id)"
        case .pivot(let p): return "zs-\(p.id)"
        case .signal(let s): return "bs-\(s.id)"
        case .established(let s): return "est-\(s.id)"
        case .divergence(let c, _, _): return "div-\(c.id)"
        case .wyckoff(let e): return "wk-\(e.id)"
        case .smc(let m, _): return "smc-\(m.id)"
        }
    }

    static func == (a: ChartElement, b: ChartElement) -> Bool { a.id == b.id }
}

/// SMC 指标里可以点开的元素。
enum SmcMark: Identifiable {
    case brk(SmcBreak)
    case orderBlock(SmcOrderBlock)
    case fvg(SmcFvg)
    case equal(SmcEqualLevel)
    case sweep(SmcSweep)
    /// 溢价 / 折价区的 50% 中位线
    case zone(SmcZone)
    /// 强 / 弱高低点：isHigh 表示高点
    case extreme(SmcExtreme, isHigh: Bool)
    case keyLevel(SmcKeyLevel)

    var id: String {
        switch self {
        case .brk(let b): return b.id
        case .orderBlock(let o): return o.id
        case .fvg(let g): return g.id
        case .equal(let e): return e.id
        case .sweep(let w): return w.id
        case .zone: return "zone"
        case .extreme(_, let isHigh): return isHigh ? "ext-high" : "ext-low"
        case .keyLevel(let k): return k.id
        }
    }
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
        case .established(let s): return established(s)
        case .divergence(let c, let refTime, let refPrice): return divergence(c, refTime: refTime, refPrice: refPrice)
        case .wyckoff(let e): return wyckoff(e)
        case .smc(let m, let swingLen): return smc(m, swingLen: swingLen)
        }
    }

    static func price(_ v: Double) -> String { String(format: "%.2f", v) }

    static func change(_ from: Double, _ to: Double) -> String {
        guard from != 0 else { return "-" }
        return String(format: "%+.1f%%", (to - from) / from * 100)
    }

    /// 威科夫事件：只说「这是什么事件、依据哪几个数」，大白话 / 举例 / 不代表什么在词典里（点下面的「学习」）。
    private static func wyckoff(_ e: WyckoffEventMark) -> ChartExplanation {
        ChartExplanation(
            title: "\(L(e.name)) · \(e.code)",
            color: Theme.wyckoff,
            facts: [(L("时间"), e.time), (L("价格"), price(e.price)),
                    (L("量比"), String(format: "%.1f×", e.volumeRatio)),
                    (L("阶段"), L("%@ 阶段", e.phase))],
            reason: L("这是威科夫体系里的「%@」事件，按这一天的价格、成交量和它在交易区间里的位置判定。量比 = 这天成交量 ÷ 这段行情的平均成交量。它只标出结构上的位置，不是买卖信号，后续走势还需要确认。", L(e.name)),
            lessonTerm: e.name)
    }

    /// SMC 元素：只说「这是什么、依据哪几个数」，大白话 / 举例 / 不代表什么在词典里（点下面的「学习」）。
    /// 所有说明都以「只标出位置，不是买卖信号」收尾；不出现买卖导向措辞（App Store 3.1.1 / 5.2.5）。
    private static func smc(_ m: SmcMark, swingLen: Int) -> ChartExplanation {
        let note = L("它只标出结构上的位置，不是买卖信号，后续走势还需要确认。")
        func range(_ lo: Double, _ hi: Double) -> String { "\(price(lo)) – \(price(hi))" }
        switch m {
        case .brk(let b):
            let dir = b.isBull ? L("向上") : L("向下")
            let swing = b.isBull ? L("高点") : L("低点")
            let isBos = b.kind == "bos"
            let reason = isBos
                ? L("收盘价%@越过了最近一个已确认的摆动%@，方向和之前的结构一致，这叫结构突破（BOS）。摆动点 = 左右各 %lld 根 K 线里最高 / 最低的那个点。", dir, swing, swingLen)
                : L("收盘价%@越过了最近一个已确认的摆动%@，方向和之前的结构相反，这叫结构转变（CHoCH）。摆动点 = 左右各 %lld 根 K 线里最高 / 最低的那个点。", dir, swing, swingLen)
            return ChartExplanation(
                title: isBos ? "\(L("结构突破")) · BOS" : "\(L("结构转变")) · CHoCH",
                color: b.isBull ? Theme.smcBull : Theme.smcBear,
                facts: [(L("突破日"), b.time), (L("被突破的价位"), price(b.level)), (L("方向"), dir)],
                reason: reason + note,
                lessonTerm: isBos ? "结构突破" : "结构转变")
        case .orderBlock(let o):
            let reason = o.isBull
                ? L("向上突破发生时，从被突破的高点到突破之前，最低的那一根 K 线的整根区间，就是一个订单块。收盘价向下跌破它就失效，图上只画还没失效的。")
                : L("向下突破发生时，从被突破的低点到突破之前，最高的那一根 K 线的整根区间，就是一个订单块。收盘价向上越过它就失效，图上只画还没失效的。")
            return ChartExplanation(
                title: "\(L("订单块")) · OB",
                color: o.isBull ? Theme.smcBull : Theme.smcBear,
                facts: [(L("日期"), o.time), (L("区间"), range(o.bottom, o.top)),
                        (L("量比"), String(format: "%.1f×", o.volumeRatio))],
                reason: reason + L("量比 = 这根 K 线成交量 ÷ 这段行情的平均成交量。") + note,
                lessonTerm: "订单块")
        case .fvg(let g):
            return ChartExplanation(
                title: "\(L("公允价值缺口")) · FVG",
                color: g.isBull ? Theme.smcBull : Theme.smcBear,
                facts: [(L("日期"), g.time), (L("缺口"), range(g.bottom, g.top)),
                        (L("方向"), g.isBull ? L("向上") : L("向下"))],
                reason: L("连续三根 K 线里，第一根和第三根之间留下一段没有被覆盖的价格空档，并且中间那根的实体明显大于此前的平均实体。价格回到缺口远端就算被填补，图上只画还没填补的。") + note,
                lessonTerm: "公允价值缺口")
        case .equal(let e):
            return ChartExplanation(
                title: e.isHigh ? "\(L("等高点")) · EQH" : "\(L("等低点")) · EQL",
                color: Theme.smcNeutral,
                facts: [(L("价位"), price(e.price))],
                reason: (e.isHigh
                    ? L("相邻两个摆动高点的差小于 0.1 倍平均波幅（ATR），看起来差不多一样高，叫等高点。")
                    : L("相邻两个摆动低点的差小于 0.1 倍平均波幅（ATR），看起来差不多一样低，叫等低点。")) + note,
                lessonTerm: "等高低点")
        case .sweep(let w):
            return ChartExplanation(
                title: "\(L("流动性扫荡")) · Sweep",
                color: Theme.smcNeutral,
                facts: [(L("日期"), w.time), (L("越过的价位"), price(w.level))],
                reason: (w.isHigh
                    ? L("这天的影线越过了一个还没被收盘突破的摆动高点，但收盘又回到了它下方，叫流动性扫荡。")
                    : L("这天的影线越过了一个还没被收盘突破的摆动低点，但收盘又回到了它上方，叫流动性扫荡。")) + note,
                lessonTerm: "流动性扫荡")
        case .zone(let z):
            return ChartExplanation(
                title: L("溢价区 / 折价区"),
                color: Theme.smcNeutral,
                facts: [(L("上沿"), price(z.top)), (L("中位"), price(z.equilibrium)), (L("下沿"), price(z.bottom))],
                reason: L("取最近的摆动高点和摆动低点（之后被更高的高点 / 更低的低点延伸），它们之间 50% 以上叫溢价区、50% 以下叫折价区。它只说价格在这一段里的相对位置。") + note,
                lessonTerm: "溢价与折价")
        case .extreme(let e, let isHigh):
            let strong = e.strength == "strong"
            let name = (strong ? L("强") : L("弱")) + (isHigh ? L("高点") : L("低点"))
            return ChartExplanation(
                title: name,
                color: Theme.smcNeutral,
                facts: [(L("价位"), price(e.price))],
                reason: L("按当前的结构方向给最近的高低点起的名字：结构向下时，高点叫强高点、低点叫弱低点；结构向上时，低点叫强低点、高点叫弱高点。这只是命名，不是对后续走势的判断。") + note,
                lessonTerm: "强弱高低点")
        case .keyLevel(let k):
            let names: [String: String] = [
                "PDH": L("前日高点"), "PDL": L("前日低点"),
                "PWH": L("前周高点"), "PWL": L("前周低点"),
                "PMH": L("前月高点"), "PML": L("前月低点"),
            ]
            return ChartExplanation(
                title: "\(names[k.code] ?? k.code) · \(k.code)",
                color: Theme.smcNeutral,
                facts: [(L("价位"), price(k.price))],
                reason: L("上一个已经走完的周期里的最高 / 最低价，线从当前这个周期的第一根 K 线画起。") + note,
                lessonTerm: "前周期高低点")
        }
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
        let dates: [(String, String)] = s.displayTime == s.time
            ? [(L("时间"), s.time)]
            : [(L("成立"), s.displayTime), (L("极值 K 线"), s.time)]
        var facts: [(String, String)] = dates + [
            (L("价格"), price(s.price)),
            (L("强弱"), SignalFormatting.strengthLabel(s.strength)),
            (L("状态"), s.isCandidate ? L("待确认，不算买卖点")
                        : (s.confirmed ? L("已确认") : L("未确认，待后续K线验证"))),
        ]
        if let r = s.priceRatio {
            facts.append((L("力度比"), String(format: "%.2f", r)))
        }
        let reason = s.isCandidate
            ? s.description + "\n" + L("所在的最后一笔还在走，端点可能延伸甚至回到中枢，按缠论尚不成立；这一笔走完才算买卖点。")
            : s.description
        return ChartExplanation(title: s.isCandidate ? L("%@（待确认）", s.label) : s.label,
                                // 待确认候选不带买卖方向色（与图上灰色虚线徽标一致）
                                color: s.isCandidate ? Theme.textSecondary : (s.isBuy ? Theme.up : Theme.down),
                                facts: facts, reason: reason, lessonTerm: "买卖点")
    }

    /// 成立日标记的说明：徽标在极值 K 线、成立日更晚，说清为什么。
    private static func established(_ s: Signal) -> ChartExplanation {
        ChartExplanation(
            title: L("%@ · 成立日", s.label),
            color: s.isBuy ? Theme.up : Theme.down,
            facts: [
                (L("成立"), s.displayTime),
                (L("极值 K 线"), s.time),
                (L("价格"), price(s.price)),
            ],
            reason: L("缠论里买卖点要等后面的笔成形才算成立：这个%@的价位是 %@ 这根 K 线的极值，下一笔到 %@ 才第一次成形，所以这一天才成立。图上的徽标画在极值 K 线，虚线末端的圆点标的是成立日。", s.label, s.time, s.displayTime),
            lessonTerm: "买卖点")
    }

    private static func divergence(_ c: Stroke, refTime: String, refPrice: Double) -> ChartExplanation {
        let top = c.direction == .up
        if let area = c.areaRatio {
            // 新后端：缠论原文的趋势背驰——离开中枢的 c 段对两个中枢之间的 b 段，比 MACD 红绿柱面积
            let areaText = String(format: "%.0f%%", area * 100)
            let reason = top
                ? L("价格创出新高，但离开中枢的这一段（c 段）的 MACD 红绿柱面积只有两个中枢之间那一段（b 段）的 %@——上涨的推动力已经跟不上。", areaText)
                : L("价格创出新低，但离开中枢的这一段（c 段）的 MACD 红绿柱面积只有两个中枢之间那一段（b 段）的 %@——下跌的推动力已经跟不上。", areaText)
            var facts: [(String, String)] = [
                (L("c 段终点"), "\(c.endTime)  \(price(c.endPrice))"),
                (L("b 段终点"), "\(refTime)  \(price(refPrice))"),
                (L("MACD 面积比"), areaText),
            ]
            if let lr = c.divLengthRatio { facts.append((L("时长比"), String(format: "%.0f%%", lr * 100))) }
            if let pr = c.priceRatio { facts.append((L("价差比"), String(format: "%.0f%%", pr * 100))) }
            return ChartExplanation(
                title: c.divergenceName, color: Theme.divergence, facts: facts,
                reason: reason + "\n" + L("面积是累计值，与时长成正比：c 段通常比 b 段短得多，所以这个比例往往偏小，请连同时长比、价差比一起看。")
                    + "\n" + L("趋势背驰：前面已有两个依次同向、不重叠的中枢，对应一类买卖点。"), lessonTerm: "背驰")
        }
        // 旧后端：当前笔与前一个同向笔比价差 / 量能 / 时长
        let ratio = c.priceRatio.map { String(format: "%.2f", $0) } ?? "-"
        let reason = top
            ? L("价格创出新高，但这一笔的涨幅只有前一个同向笔的 %@ 倍，量能或时长也更弱——上涨的推动力已经跟不上。", ratio)
            : L("价格创出新低，但这一笔的跌幅只有前一个同向笔的 %@ 倍，量能或时长也更弱——下跌的推动力已经跟不上。", ratio)
        let kindNote: String
        switch c.divergenceType {
        case "trend": kindNote = L("趋势背驰：前面已有两个同向中枢，对应一类买卖点。")
        case "consolidation": kindNote = L("盘整背驰：前面只有一个中枢。「严格」口径下不对应一类买卖点；「中等」「宽松」口径下可能对应。")
        default: kindNote = ""
        }
        return ChartExplanation(
            title: c.divergenceName, color: Theme.divergence,
            facts: [
                (L("本笔"), "\(c.startTime) → \(c.endTime)  \(change(c.startPrice, c.endPrice))"),
                (L("参照点"), "\(refTime)  \(price(refPrice))"),
                (L("价差比"), ratio),
            ],
            reason: kindNote.isEmpty ? reason : reason + "\n" + kindNote, lessonTerm: "背驰")
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
