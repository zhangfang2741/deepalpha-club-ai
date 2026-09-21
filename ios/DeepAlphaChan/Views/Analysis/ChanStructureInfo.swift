import SwiftUI

/// 结构视图（ChanStructureView）里每一个可点元素的引用。
///
/// 点框/带/点/状态色块都对应一个 ChanRef，用它驱动底部弹层的详情。Identifiable
/// 以便 `.sheet(item:)` 使用。
enum ChanRef: Identifiable, Hashable {
    case trend                    // 走势（大级别）名字
    case divergence               // 背驰监测
    case regime(String)           // 走势两分色块：range / up / down
    case pivot(Int)               // 第 i 个中枢（strokePivots 下标）
    case stage(String)            // 当前中枢生命周期色块：form / osc / leave / pull
    case signal                   // 买卖点（点）
    case segment                  // 线段名字
    case segDir(Bool)             // 线段方向色块（true=向上）
    case stroke                   // 笔名字
    case strokeState(Bool)        // 笔状态色块（true=形成中）

    var id: String {
        switch self {
        case .trend: return "trend"
        case .divergence: return "div"
        case .regime(let k): return "regime-\(k)"
        case .pivot(let i): return "pivot-\(i)"
        case .stage(let s): return "stage-\(s)"
        case .signal: return "signal"
        case .segment: return "seg"
        case .segDir(let up): return "segdir-\(up)"
        case .stroke: return "stroke"
        case .strokeState(let f): return "strokest-\(f)"
        }
    }
}

/// 弹层里展示的一条详情：名称 + 标签 + 配色 + 「为什么」+ 概念，以及可选的附加块
/// （买卖点三类对照 / 走势退化对照）与是否可下钻。
struct ChanTopic {
    let name: String
    let tag: String
    let color: Color
    let lead: String
    let why: String
    let concept: String
    var extra: Extra = .none
    var drillable: Bool = false

    enum Extra { case none, buyTypes, regime }
}

/// 把 ChanAnalysis 的结构数据规则化成 ChanRef → ChanTopic，以及各处的当前状态判定。
/// 全部数据驱动（与 ChanEvidence / ChanPhase 同口径），不写死场景。
enum ChanStructureInfo {

    // MARK: - 基础判定

    static func walkKey(_ a: ChanAnalysis) -> String { a.walkType ?? "none" }

    static func trendColor(_ a: ChanAnalysis) -> Color {
        switch walkKey(a) {
        case "up_trend": return Theme.up
        case "down_trend": return Theme.down
        default: return Theme.segment
        }
    }

    /// 现价相对最近中枢的位置：above / below / inside；无中枢返回 nil。
    static func pivotPosition(_ a: ChanAnalysis) -> (pivot: Pivot, close: Double, pos: String)? {
        guard let p = a.strokePivots.last, let close = a.mergedCandles.last?.close else { return nil }
        if close > p.zg { return (p, close, "above") }
        if close < p.zd { return (p, close, "below") }
        return (p, close, "inside")
    }

    static func latestSignal(_ a: ChanAnalysis) -> Signal? {
        a.signals.sorted { $0.time > $1.time }.first
    }

    /// 是否已出现「已确认的三类买卖点」（用于判定中枢离开→回抽是否确认）。
    static func hasConfirmedThird(_ a: ChanAnalysis) -> Bool {
        a.signals.contains { ($0.type == .buy3 || $0.type == .sell3) && $0.confirmed }
    }

    /// 背驰：top（顶背驰）/ bottom（底背驰）/ none，由 trend_outlook 反推（reversal 才是终结性背驰）。
    static func divergenceKey(_ a: ChanAnalysis) -> String {
        switch a.trendOutlook ?? "" {
        case "reversal_down": return "top"
        case "reversal_up": return "bottom"
        default: return "none"
        }
    }

    /// 当前中枢生命周期所处：form / osc / leave / pull。
    static func currentStage(_ a: ChanAnalysis) -> String {
        guard let info = pivotPosition(a) else { return "none" }
        if info.pos == "inside" { return "osc" }
        return hasConfirmedThird(a) ? "pull" : "leave"
    }

    /// 生命周期四步各自的显示态：done（已过）/ current（当前）/ future（待定）。
    static func stageStatus(_ a: ChanAnalysis, _ step: String) -> ChipStatus {
        let cur = currentStage(a)
        guard cur != "none" else { return .future }
        let order = ["form", "osc", "leave", "pull"]
        guard let ci = order.firstIndex(of: cur), let si = order.firstIndex(of: step) else { return .future }
        if si < ci { return .done }
        if si == ci { return .current }
        return .future
    }

    // MARK: - 失效价（把候选变可检验）

    /// 最近一个「未确认」的买卖点的失效价：买点=跌回中枢下沿破 ZG 即废（回到中枢内），
    /// 卖点=升回中枢上沿。返回 (失效价, 是否买点)；无未确认信号返回 nil。
    static func invalidation(_ a: ChanAnalysis) -> (price: Double, isBuy: Bool)? {
        guard let s = latestSignal(a), !s.confirmed, let p = a.strokePivots.last else { return nil }
        return (s.isBuy ? p.zg : p.zd, s.isBuy)
    }

    // MARK: - ChanRef → ChanTopic

    static func topic(for ref: ChanRef, in a: ChanAnalysis) -> ChanTopic {
        switch ref {
        case .trend:
            return ChanTopic(
                name: L("走势（大级别）"), tag: L("结构"), color: trendColor(a), lead: L("是什么"),
                why: trendWhy(a),
                concept: L("走势分类：任何级别只有盘整 / 趋势两类；趋势=≥2 个同向中枢。"),
                extra: .regime)

        case .regime(let k):
            return regimeTopic(k, a)

        case .divergence:
            return divergenceTopic(a)

        case .pivot(let i):
            return pivotTopic(i, a)

        case .stage(let s):
            return stageTopic(s, a)

        case .signal:
            return signalTopic(a)

        case .segment:
            return ChanTopic(
                name: L("线段"), tag: L("结构"), color: Theme.segment, lead: L("是什么"),
                why: L("由至少 3 笔搭成（走势 ⊃ 线段 ⊃ 笔），代表中期方向。"),
                concept: L("线段是大级别趋势的组成块。"))

        case .segDir(let up):
            let cur = a.segments.last?.direction
            let isCurrent = (cur == .up) == up && cur != nil
            return ChanTopic(
                name: up ? L("线段向上") : L("线段向下"),
                tag: isCurrent ? L("当前") : L("未处于"),
                color: Theme.segment, lead: isCurrent ? L("为什么") : L("是什么"),
                why: isCurrent
                    ? L("当前这一笔尚未破坏线段结构，所以线段仍是这个方向、未结束。")
                    : L("线段当前不在这个方向。"),
                concept: "")

        case .stroke:
            return ChanTopic(
                name: L("笔"), tag: L("结构"), color: Theme.stroke, lead: L("是什么"),
                why: L("相邻一顶一底的连线，隶属链最小一环，最小的方向单位。"),
                concept: "")

        case .strokeState(let forming):
            let isForming = !(a.strokes.last?.confirmed ?? true)
            let isCurrent = forming == isForming
            return ChanTopic(
                name: forming ? L("笔 · 形成中") : L("笔 · 已确认"),
                tag: isCurrent ? L("当前") : (forming ? L("已过") : L("未来")),
                color: Theme.stroke, lead: isCurrent ? L("为什么") : L("要什么"),
                why: forming
                    ? L("最新分型后延伸、另一端分型尚未确认，这一笔还在走（未确认=虚线）。")
                    : L("要等末端分型确认后，这一笔才算走完。"),
                concept: "")
        }
    }

    // MARK: - 各结构的「为什么」

    private static func trendWhy(_ a: ChanAnalysis) -> String {
        let n = a.strokePivots.count
        switch walkKey(a) {
        case "up_trend": return L("%lld 个中枢依次抬高 = 上涨趋势。它是所有小级别动作的背景。", n)
        case "down_trend": return L("%lld 个中枢依次降低 = 下跌趋势。它是所有小级别动作的背景。", n)
        case "consolidation": return L("只有一个中枢，价在区间内反复 = 盘整，方向未定。")
        default: return L("尚未形成中枢，单边推进或数据不足，走势未定。")
        }
    }

    private static func regimeTopic(_ k: String, _ a: ChanAnalysis) -> ChanTopic {
        let cur = walkKey(a)
        let isCur: Bool
        switch k {
        case "range": isCur = cur == "consolidation"
        case "up": isCur = cur == "up_trend"
        default: isCur = cur == "down_trend"
        }
        let name = k == "range" ? L("盘整") : (k == "up" ? L("上涨趋势") : L("下跌趋势"))
        let why: String
        switch k {
        case "range": why = L("只有一个中枢的走势，价在区间内反复。")
        case "up": why = L("≥2 个依次抬高的中枢。")
        default: why = L("≥2 个依次降低的中枢。")
        }
        return ChanTopic(
            name: name, tag: isCur ? L("当前") : L("未处于"),
            color: trendColor(a), lead: isCur ? L("为什么") : L("是什么"),
            why: isCur ? L("%1$@ 当前走势正是如此。", why) : why,
            concept: L("带的条数与排布本身就是盘整 / 趋势的定义。"),
            extra: .regime)
    }

    private static func divergenceTopic(_ a: ChanAnalysis) -> ChanTopic {
        let k = divergenceKey(a)
        let tag = k == "none" ? L("未出现") : L("已显现")
        let why: String
        switch k {
        case "top": why = L("上涨末端出现顶背驰：价创新高但动能没跟上，可能转下跌。")
        case "bottom": why = L("下跌末端出现底背驰：价创新低但动能减弱，可能转上涨（一买结构）。")
        default: why = L("当前未出现背驰，推动力度仍在。")
        }
        return ChanTopic(
            name: L("背驰监测"), tag: tag, color: Theme.segment, lead: L("是什么"),
            why: why,
            concept: L("背驰=面积缩小且 DIF 峰值不再新高；背驰—转折定理：它是级别转折的唯一技术依据。"))
    }

    private static func pivotTopic(_ i: Int, _ a: ChanAnalysis) -> ChanTopic {
        let pivots = a.strokePivots
        guard i >= 0, i < pivots.count else {
            return ChanTopic(name: L("中枢"), tag: L("尚未形成"), color: Theme.pivotFill,
                             lead: L("是什么"),
                             why: L("重叠不足三段，还没围出中枢——只有单边推进。"),
                             concept: L("中枢=≥3 段走势重叠的价格带。"))
        }
        let p = pivots[i]
        let isLatest = i == pivots.count - 1
        let range = "\(fmt(p.zd))–\(fmt(p.zg))"
        return ChanTopic(
            name: L("中枢%1$@ %2$@", ordinal(i, count: pivots.count), range),
            tag: isLatest ? L("当前") : L("已完成"),
            color: Theme.pivotFill, lead: L("是什么"),
            why: isLatest
                ? L("下面这些笔 / 线段重叠围出的区间带（ZG %1$@ / ZD %2$@），趋势里最新的中枢。", fmt(p.zg), fmt(p.zd))
                : L("更早的中枢，已被走势离开；它与其它中枢的排布决定了走势是盘整还是趋势。"),
            concept: L("中枢=重叠区，不是更深一层框；可下钻看它内部的次级别。"),
            drillable: true)
    }

    private static func stageTopic(_ s: String, _ a: ChanAnalysis) -> ChanTopic {
        let status = stageStatus(a, s)
        let tag: String
        switch status {
        case .done: tag = L("已过")
        case .current: tag = L("当前")
        case .future: tag = L("未来")
        }
        let name: String
        let why: String
        switch s {
        case "form":
            name = L("中枢 · 形成"); why = L("三段次级别走势重叠，围出 ZG–ZD 区间。")
        case "osc":
            name = L("中枢 · 震荡"); why = L("价格在 ZG–ZD 内反复、中枢延伸。")
        case "leave":
            name = L("中枢 · 离开"); why = L("次级别走势带价离开中枢区间；离开是否成立要看接下来的回抽。")
        default:
            name = L("中枢 · 回抽"); why = L("离开后回抽：不进中枢→买卖点成立；进中枢→回到震荡。不预言。")
        }
        return ChanTopic(name: name, tag: tag, color: Theme.pivotFill,
                         lead: status == .future ? L("要什么") : L("为什么"),
                         why: why,
                         concept: L("中枢生命周期：形成 → 震荡 → 离开 → 回抽。"),
                         drillable: true)
    }

    private static func signalTopic(_ a: ChanAnalysis) -> ChanTopic {
        guard let s = latestSignal(a) else {
            return ChanTopic(name: L("买卖点"), tag: L("暂无"), color: Theme.accent, lead: L("是什么"),
                             why: L("当前区间尚未识别到明确买卖点。"),
                             concept: L("买卖点必依附具体级别与中枢的进出。"), extra: .buyTypes)
        }
        let color = s.isBuy ? Theme.up : Theme.down
        let tag = s.confirmed ? L("已确认") : L("候选")
        var why = s.confirmed
            ? L("离开与回抽结构均已完成确认。")
            : L("落在未确认笔上，为左侧预判（候选）。")
        if let inv = invalidation(a) {
            why += L(" 失效价 %1$@：%2$@即废。", fmt(inv.price), inv.isBuy ? L("跌回中枢内") : L("升回中枢内"))
        }
        return ChanTopic(
            name: L("买卖点 · %@", s.label), tag: tag, color: color, lead: L("为什么"),
            why: why,
            concept: L("三类各挂不同位置：一买 / 一卖=趋势末端背驰、二类=回抽不破、三类=离开中枢不回。"),
            extra: .buyTypes)
    }

    // MARK: - 工具

    static func fmt(_ v: Double) -> String { String(format: "%.2f", v) }

    private static func ordinal(_ i: Int, count: Int) -> String {
        // 只有一个中枢时不加序号；多个时用 ①②③…
        guard count > 1 else { return "" }
        let marks = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
        return i < marks.count ? marks[i] : "\(i + 1)"
    }
}

/// 状态色块 / 生命周期步骤的三态。
enum ChipStatus { case done, current, future }
