import SwiftUI

/// 各词条的示意图数据。
///
/// 放在 Swift 而不是 lessons.json：这些是矢量图形的几何描述，塞进 JSON 会变成
/// 一堆没人看得懂的数字，改起来比改代码还难。正文文案仍在 JSON 里，可以随便改。
///
/// 画笔、中枢的图用 Zigzag 由转折点生成K线：一笔跨好几根K线，跟分析页上看到的一致。
/// 中枢方框的上下沿按缠论定义手算（上沿 = 前三笔高点里最低的，下沿 = 低点里最高的），
/// 改转折点时要一起改。
enum LessonDiagrams {

    static func spec(for lessonID: String) -> DiagramSpec? {
        switch lessonID {
        case "inclusion":    return inclusion
        case "fractal":      return fractal
        case "stroke":       return stroke
        case "segment":      return segment
        case "pivot":        return pivot
        case "divergence":   return divergence
        case "macd":         return macd
        case "trade-points": return tradePoints
        case "level":        return level
        default:             return nil
        }
    }

    /// 包含处理：第 2、3 根是包含关系（第 3 根的高低点都落在第 2 根区间内），
    /// 第 6 根是合并结果。之前在涨，所以高点取高（0.72）、低点也取高（0.38）。
    ///
    /// 这张图必须手写 OHLC。用收盘价推导的话画不出「一根完全罩住另一根」。
    private static var inclusion: DiagramSpec {
        DiagramSpec(
            candles: [
                .init(open: 0.30, high: 0.40, low: 0.26, close: 0.36),
                // 大阳线：区间 0.30–0.72
                .init(open: 0.34, high: 0.72, low: 0.30, close: 0.66),
                // 被完全包住：高 0.64 < 0.72，低 0.38 > 0.30
                .init(open: 0.58, high: 0.64, low: 0.38, close: 0.44),
                // 留白，把「原始」和「合并后」分开
                .init(open: 0.50, high: 0.50, low: 0.50, close: 0.50),
                .init(open: 0.50, high: 0.50, low: 0.50, close: 0.50),
                // 合并结果：高取两者较高 0.72，低取两者较高 0.38
                .init(open: 0.40, high: 0.72, low: 0.38, close: 0.66),
            ],
            labels: [
                .init(at: 2, anchor: .value(0.72), text: L("后一根被完全包住"), color: Theme.segment),
                .init(at: 5, anchor: .value(0.72), text: L("合并为一根"), color: Theme.textPrimary),
                .init(at: 5, anchor: .low, text: L("高取高 · 低取高"), color: Theme.textSecondary, above: false),
                .init(at: 4, anchor: .value(0.50), text: "⟹", color: Theme.textSecondary),
            ],
            emphases: [
                .init(from: 1, to: 2, top: 0.74, bottom: 0.28,
                      color: Theme.segment, alpha: 0.10),
            ]
        )
    }

    /// 分型：左边三根是顶分型，右边三根是底分型。
    ///
    /// 手写 OHLC：顶分型要求中间那根高点最高、低点也最高，用收盘价推导的蜡烛
    /// 满足不了第二个条件，教定义却画了个不合定义的图，比不配图更糟。
    private static var fractal: DiagramSpec {
        DiagramSpec(
            candles: [
                .init(open: 0.30, high: 0.40, low: 0.26, close: 0.38),
                .init(open: 0.38, high: 0.58, low: 0.34, close: 0.54),
                // 顶：高 0.80、低 0.50 都是 1–3 根里最高的
                .init(open: 0.54, high: 0.80, low: 0.50, close: 0.72),
                .init(open: 0.70, high: 0.72, low: 0.44, close: 0.48),
                .init(open: 0.48, high: 0.52, low: 0.30, close: 0.34),
                // 底：低 0.14、高 0.38 都是 4–6 根里最低的
                .init(open: 0.34, high: 0.38, low: 0.14, close: 0.18),
                .init(open: 0.20, high: 0.46, low: 0.18, close: 0.42),
            ],
            fractals: [
                .init(at: 2, isTop: true),
                .init(at: 5, isTop: false),
            ],
            labels: [
                .init(at: 2, anchor: .high, text: L("顶分型"), color: Theme.topFractal, extraOffset: 10),
                .init(at: 5, anchor: .low, text: L("底分型"), color: Theme.bottomFractal, above: false, extraOffset: 10),
            ],
            emphases: [
                .init(from: 1, to: 3, top: 0.82, bottom: 0.32, color: Theme.topFractal, alpha: 0.08),
                .init(from: 4, to: 6, top: 0.54, bottom: 0.12, color: Theme.bottomFractal, alpha: 0.08),
            ]
        )
    }

    /// 笔：底分型连到顶分型是一笔向上；最后一笔还在走，画虚线。
    private static var stroke: DiagramSpec {
        let z = Zigzag(turns: [0.46, 0.16, 0.84, 0.48], legBars: 4)
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(from: 1, dashedLast: true),
            fractals: [
                .init(at: z.t(1), isTop: false),
                .init(at: z.t(2), isTop: true),
            ],
            labels: [
                .init(at: z.t(1) + 3, anchor: .value(0.36), text: L("一笔"), color: Theme.stroke, above: false),
                .init(at: z.t(1), anchor: .low, text: L("底分型"), color: Theme.bottomFractal, above: false, extraOffset: 10),
                .init(at: z.t(2), anchor: .high, text: L("顶分型"), color: Theme.topFractal, extraOffset: 10),
                .init(at: z.t(3), anchor: .low, text: L("虚线 = 未确认"), color: Theme.textSecondary, above: false),
            ]
        )
    }

    /// 线段：五笔（蓝）一上一下、整体向上，合成一条向上线段（橙）。
    private static var segment: DiagramSpec {
        let z = Zigzag(turns: [0.12, 0.40, 0.26, 0.58, 0.44, 0.86, 0.60])
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(dashedLast: true),
            segments: [z.conn(0, 5)],
            labels: [
                .init(at: z.t(2), anchor: .value(0.86), text: L("线段 = 至少三笔"), color: Theme.segment),
                .init(at: z.t(1), anchor: .high, text: L("笔"), color: Theme.stroke),
            ]
        )
    }

    /// 中枢：1→2、2→3、3→4 三笔重叠，上沿 = min(0.64, 0.68, 0.68)，下沿 = max(0.40, 0.40, 0.44)；
    /// 4→5 向上离开，5→6 回落停在上沿之上，没回到中枢。
    private static var pivot: DiagramSpec {
        let z = Zigzag(turns: [0.12, 0.64, 0.40, 0.68, 0.44, 0.90, 0.72])
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(dashedLast: true),
            pivots: [.init(from: z.t(1), to: z.t(4), top: 0.64, bottom: 0.44)],
            labels: [
                // 标在方框下方：框内被笔穿来穿去，文字放进去会压在K线上
                .init(at: z.t(2) + 1, anchor: .value(0.38), text: L("示意图·中枢"),
                      color: Theme.pivotFill, above: false),
                .init(at: z.t(5), anchor: .high, text: L("离开中枢"), color: Theme.up),
                // 放到回落笔下方的空白处，贴着低点放会压到K线（英文标签更长）
                .init(at: z.t(6), anchor: .value(0.62), text: L("回落不回中枢"), color: Theme.textSecondary, above: false),
            ]
        )
    }

    /// 背驰：两段上涨，第二段创新高但价差只有第一段的 0.58 倍（0.30 / 0.52）。
    /// 画法与分析页一致：粉色实线连起两段终点，标「趋势背驰 + 面积比」。
    private static var divergence: DiagramSpec {
        let z = Zigzag(turns: [0.10, 0.62, 0.40, 0.70, 0.50])
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(dashedLast: true),
            labels: [
                .init(at: z.t(1) - 2, anchor: .value(0.80), text: L("第一段：涨得多"),
                      color: Theme.textSecondary, above: false),
                .init(at: z.t(3), anchor: .value(0.30), text: L("第二段：创新高、涨得少"),
                      color: Theme.textSecondary, above: false),
                .init(at: z.t(2), anchor: .value(0.70), text: L("趋势背驰") + " 0.58",
                      color: Theme.divergence, extraOffset: 6),
            ],
            divergences: [z.conn(1, 3)]
        )
    }

    /// MACD：柱、DIF/DEA。缠论原文用红绿柱面积比较背驰力度；App 里买卖点的一类背驰默认用它，图上的背驰标注不用。
    private static var macd: DiagramSpec {
        .fromPath(
            [0.20, 0.36, 0.54, 0.70, 0.78, 0.62, 0.48, 0.40, 0.52],
            labels: [
                .init(at: 4, anchor: .high, text: L("价格见顶回落"), color: Theme.textSecondary),
            ],
            macdBars: [0.25, 0.60, 0.88, 0.95, 0.55, 0.10, -0.40, -0.72, -0.50],
            // DIF 在 DEA 上方时柱为正，交叉下穿后柱翻负——三者的关系要能对上
            macdDIF: [0.20, 0.55, 0.85, 0.92, 0.62, 0.18, -0.30, -0.65, -0.48],
            macdDEA: [0.10, 0.28, 0.50, 0.68, 0.70, 0.55, 0.20, -0.15, -0.38],
            macdLabels: [
                .init(at: 3, anchor: .value(0.95), text: L("红柱放大 = 多方占优"), color: Theme.up),
                // 锚在 -0.4 而不是最低的 -0.72，否则标注会贴到卡片底边
                .init(at: 7, anchor: .value(-0.40), text: L("翻绿 = 空方占优"), color: Theme.down, above: false),
            ]
        )
    }

    /// 三类买点全过程，按缠论原文：
    /// - 下跌趋势：中枢 A（0.80–0.86）、中枢 B（0.46–0.54）依次下移、不重叠；
    /// - 一买：离开 B 的一段（0.54→0.30）创新低，但价差只有离开 A 那段（0.86→0.44）的 0.57 倍 → 趋势背驰（前面已有两个依次下移的中枢）；
    /// - 二买：一买后第一次回落，低点 0.36 没破 0.30；
    /// - 新中枢 C（0.36–0.46），13→14 从中枢内向上离开，14→15 第一次回落停在 0.56 > 上沿 → 三买。
    private static var tradePoints: DiagramSpec {
        let z = Zigzag(turns: [0.96, 0.80, 0.90, 0.78, 0.86, 0.44, 0.56, 0.46, 0.54,
                               0.30, 0.46, 0.36, 0.50, 0.40, 0.74, 0.56, 0.82],
                       legBars: 2)
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(dashedLast: true),
            pivots: [
                .init(from: z.t(1), to: z.t(4), top: 0.86, bottom: 0.80),
                .init(from: z.t(5), to: z.t(8), top: 0.54, bottom: 0.46),
                .init(from: z.t(9), to: z.t(13), top: 0.46, bottom: 0.36),
            ],
            labels: [
                .init(at: (z.t(1) + z.t(4)) / 2, anchor: .value(0.90), text: L("示意图·中枢"), color: Theme.pivotFill),
                .init(at: (z.t(5) + z.t(8)) / 2, anchor: .value(0.56), text: L("示意图·中枢"), color: Theme.pivotFill),
                .init(at: z.t(7), anchor: .value(0.37), text: L("趋势背驰"), color: Theme.divergence, above: false),
                .init(at: z.t(9), anchor: .low, text: L("一买"), color: Theme.up, above: false, extraOffset: 2),
                .init(at: z.t(11), anchor: .low, text: L("二买"), color: Theme.up, above: false, extraOffset: 2),
                .init(at: z.t(15), anchor: .low, text: L("三买"), color: Theme.up, above: false, extraOffset: 2),
            ],
            divergences: [z.conn(5, 9)],
            height: 200
        )
    }

    /// 走势级别：大级别的一笔向上（橙），放大看是小级别的一整段走势——
    /// 里面有自己的中枢（上沿 min(0.36,0.40,0.40)、下沿 max(0.20,0.20,0.24)），
    /// 离开中枢后的第一次回落不回中枢，是小级别三买：与大级别方向一致，即「共振」。
    private static var level: DiagramSpec {
        let z = Zigzag(turns: [0.10, 0.36, 0.20, 0.40, 0.24, 0.38, 0.26, 0.60, 0.46, 0.74, 0.62, 0.90],
                       legBars: 2)
        return DiagramSpec(
            candles: z.candles,
            strokes: z.strokes(),
            segments: [z.conn(0, 11)],
            pivots: [.init(from: z.t(1), to: z.t(6), top: 0.36, bottom: 0.24, alpha: 0.16)],
            labels: [
                .init(at: z.t(4), anchor: .value(0.80), text: L("大级别：一笔向上"), color: Theme.segment),
                .init(at: z.t(3), anchor: .value(0.18), text: L("小级别：内部有中枢"),
                      color: Theme.pivotFill, above: false),
                .init(at: z.t(8) + 1, anchor: .low, text: L("小级别三买"), color: Theme.up, above: false),
            ]
        )
    }
}
