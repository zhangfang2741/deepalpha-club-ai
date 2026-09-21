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
                why: L("由好几段小波动接起来的一段，代表中期的方向。"),
                concept: L("线段是大级别趋势的组成块。"))

        case .segDir(let up):
            let cur = a.segments.last?.direction
            let isCurrent = (cur == .up) == up && cur != nil
            return ChanTopic(
                name: up ? L("线段向上") : L("线段向下"),
                tag: isCurrent ? L("当前") : L("未处于"),
                color: Theme.segment, lead: isCurrent ? L("为什么") : L("是什么"),
                why: isCurrent
                    ? L("最近这个小波动还没把中期方向掰过来，所以中期还是这个方向、还没走完。")
                    : L("中期现在不是这个方向。"),
                concept: "")

        case .stroke:
            return ChanTopic(
                name: L("笔"), tag: L("结构"), color: Theme.stroke, lead: L("是什么"),
                why: L("就是价格最小的一上一下、一小段方向。"),
                concept: "")

        case .strokeState(let forming):
            let isForming = !(a.strokes.last?.confirmed ?? true)
            let isCurrent = forming == isForming
            return ChanTopic(
                name: forming ? L("笔 · 形成中") : L("笔 · 已确认"),
                tag: isCurrent ? L("当前") : (forming ? L("已过") : L("未来")),
                color: Theme.stroke, lead: isCurrent ? L("为什么") : L("要什么"),
                why: forming
                    ? L("最近这一小段还在走、还没走完（没走完的用虚线画）。")
                    : L("要等它走完、被后面的走势确认，才算数。"),
                concept: "")
        }
    }

    // MARK: - 各结构的「为什么」

    private static func trendWhy(_ a: ChanAnalysis) -> String {
        switch walkKey(a) {
        case "up_trend": return L("价格一波比一波高，整体在往上走。下面那些小的涨跌，都发生在这个上涨大方向里。")
        case "down_trend": return L("价格一波比一波低，整体在往下走。下面那些小反弹，都还在这个下跌大方向里。")
        case "consolidation": return L("价格在一个区间里来回晃，没走出明确方向，就是横着震荡。")
        default: return L("目前还没走出清楚的结构，方向看不准。")
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
        case "range": why = L("价格在一个区间里来回晃、没方向。")
        case "up": why = L("价格一波比一波高。")
        default: why = L("价格一波比一波低。")
        }
        return ChanTopic(
            name: name, tag: isCur ? L("当前") : L("未处于"),
            color: trendColor(a), lead: isCur ? L("为什么") : L("是什么"),
            why: isCur ? L("%1$@ 现在走的就是这种。", why) : why,
            concept: L("带的条数与排布本身就是盘整 / 趋势的定义。"),
            extra: .regime)
    }

    private static func divergenceTopic(_ a: ChanAnalysis) -> ChanTopic {
        let k = divergenceKey(a)
        let tag = k == "none" ? L("未出现") : L("已显现")
        let why: String
        switch k {
        case "top": why = L("涨到后面劲不够了：价格还在创新高，但上涨的力气明显变弱，容易冲高回落。")
        case "bottom": why = L("跌到后面劲不够了：价格还在创新低，但下跌的力气在减弱，容易见底反弹。")
        default: why = L("眼下推动的劲头还在，没看到明显减弱。")
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
                             why: L("价格还没在一块区间里反复重叠出争夺区，眼下一直在单边走。"),
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
                ? L("最近多空反复争夺的一段价格区间（%1$@ 到 %2$@），是由下面那些小波动来回重叠出来的。", fmt(p.zd), fmt(p.zg))
                : L("更早的一段争夺区间，价格已经走出去了。它和别的区间怎么排，决定了是横盘还是趋势。"),
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
            name = L("中枢 · 形成"); why = L("价格在一小段区间里来回，重叠出了一块区域。")
        case "osc":
            name = L("中枢 · 震荡"); why = L("价格还在这块区域里上上下下地晃。")
        case "leave":
            name = L("中枢 · 离开"); why = L("价格已经跑出这块区域了；算不算真突破，还要看会不会又被拉回来。")
        default:
            name = L("中枢 · 回抽"); why = L("跑出去之后回头拉一下：不再回到区域里 → 信号成立；又回到里面 → 继续横盘。这一步还没发生，先不下结论。")
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
                             why: L("这段行情还没找到明确的买卖点。"),
                             concept: L("买卖点必依附具体级别与中枢的进出。"), extra: .buyTypes)
        }
        let color = s.isBuy ? Theme.up : Theme.down
        let tag = s.confirmed ? L("已确认") : L("候选")
        var why = s.confirmed
            ? L("该走的都走完了，这个信号已经成立。")
            : L("信号刚冒头、走势还没走完，属于提前预判，不一定成。")
        if let inv = invalidation(a) {
            why += L(" 要是价格%1$@ %2$@ 那一带（又回到争夺区里），这个信号就作废。",
                     inv.isBuy ? L("跌回") : L("涨回"), fmt(inv.price))
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
