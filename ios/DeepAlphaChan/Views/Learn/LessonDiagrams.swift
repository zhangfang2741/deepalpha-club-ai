import SwiftUI

/// 各词条的示意图数据。
///
/// 放在 Swift 而不是 lessons.json：这些是矢量图形的几何描述，塞进 JSON 会变成
/// 一堆没人看得懂的数字，改起来比改代码还难。正文文案仍在 JSON 里，可以随便改。
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

    /// 包含处理：第 2、3 根是真正的包含关系（第 3 根的高低点都落在第 2 根区间内），
    /// 第 5 根是合并后的等效单根。
    ///
    /// 这张图必须手写 OHLC。用收盘价推导的话画不出「一根完全罩住另一根」，
    /// 教包含关系却画不出包含关系，比不配图更糟。
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
                // 合并结果：取两根的整体区间
                .init(open: 0.34, high: 0.72, low: 0.30, close: 0.66),
            ],
            labels: [
                .init(at: 2, anchor: .value(0.72), text: L("后一根被完全包住"), color: Theme.segment),
                .init(at: 5, anchor: .value(0.72), text: L("合并为一根"), color: Theme.textPrimary),
                .init(at: 4, anchor: .value(0.50), text: "⟹", color: Theme.textSecondary),
            ],
            emphases: [
                .init(from: 1, to: 2, top: 0.74, bottom: 0.28,
                      color: Theme.segment, alpha: 0.10),
            ]
        )
    }

    /// 分型：一个顶分型、一个底分型，各由三根构成。
    private static var fractal: DiagramSpec {
        .fromPath(
            [0.32, 0.50, 0.76, 0.52, 0.34, 0.18, 0.36, 0.54],
            fractals: [
                .init(at: 2, isTop: true),
                .init(at: 5, isTop: false),
            ],
            labels: [
                .init(at: 2, anchor: .high, text: L("顶分型"), color: Theme.topFractal, extraOffset: 10),
                .init(at: 5, anchor: .low, text: L("底分型"), color: Theme.bottomFractal, above: false, extraOffset: 10),
            ]
        )
    }

    /// 笔：底分型到顶分型连一条，中间隔着独立 K 线。
    private static var stroke: DiagramSpec {
        .fromPath(
            [0.44, 0.20, 0.34, 0.48, 0.64, 0.80, 0.62],
            strokes: [.init(from: 1, to: 5, fromEdge: .low, toEdge: .high)],
            fractals: [
                .init(at: 1, isTop: false),
                .init(at: 5, isTop: true),
            ],
            labels: [
                .init(at: 3, anchor: .value(0.40), text: L("一笔"), color: Theme.stroke, above: false),
                .init(at: 1, anchor: .low, text: L("底分型"), color: Theme.bottomFractal, above: false, extraOffset: 10),
                .init(at: 5, anchor: .high, text: L("顶分型"), color: Theme.topFractal, extraOffset: 10),
            ]
        )
    }

    /// 线段：多笔（蓝）叠成一个线段（橙），笔之间有价格重叠。
    private static var segment: DiagramSpec {
        .fromPath(
            [0.18, 0.30, 0.52, 0.38, 0.60, 0.46, 0.74, 0.84],
            strokes: [
                .init(from: 0, to: 2, fromEdge: .low, toEdge: .high),
                .init(from: 2, to: 3, fromEdge: .high, toEdge: .low),
                .init(from: 3, to: 4, fromEdge: .low, toEdge: .high),
                .init(from: 4, to: 5, fromEdge: .high, toEdge: .low),
                .init(from: 5, to: 7, fromEdge: .low, toEdge: .high),
            ],
            segments: [.init(from: 0, to: 7, fromEdge: .low, toEdge: .high)],
            labels: [
                .init(at: 3, anchor: .value(0.92), text: L("线段 = 至少三笔"), color: Theme.segment),
                .init(at: 2, anchor: .value(0.60), text: L("笔"), color: Theme.stroke),
            ]
        )
    }

    /// 中枢：连续三段的重叠区间，最后一段离开中枢。
    private static var pivot: DiagramSpec {
        .fromPath(
            [0.16, 0.44, 0.70, 0.40, 0.72, 0.38, 0.66, 0.90],
            strokes: [
                .init(from: 0, to: 2, fromEdge: .low, toEdge: .high),
                .init(from: 2, to: 3, fromEdge: .high, toEdge: .low),
                .init(from: 3, to: 4, fromEdge: .low, toEdge: .high),
                .init(from: 4, to: 5, fromEdge: .high, toEdge: .low),
                .init(from: 5, to: 6, fromEdge: .low, toEdge: .high),
                .init(from: 6, to: 7, fromEdge: .high, toEdge: .high),
            ],
            pivots: [.init(from: 2, to: 6, top: 0.66, bottom: 0.44)],
            labels: [
                .init(at: 4, anchor: .value(0.30), text: L("中枢 = 三段重叠区"), color: Theme.pivotFill, above: false),
                .init(at: 7, anchor: .value(0.94), text: L("离开中枢"), color: Theme.up),
            ]
        )
    }

    /// 背驰：价格创新高，但 MACD 柱面积明显缩小。
    ///
    /// 必须画 MACD。这个 App 判定背驰用的就是 MACD 面积比，只画两段斜率不同的
    /// 价格线，展示的是「斜率变缓」而不是背驰的定义——学的人对不上买卖点卡片里
    /// 那个「面积比 0.58」是怎么来的。
    private static var divergence: DiagramSpec {
        .fromPath(
            [0.16, 0.34, 0.58, 0.72, 0.52, 0.44, 0.58, 0.72, 0.82],
            segments: [
                .init(from: 0, to: 3, fromEdge: .low, toEdge: .high),
                .init(from: 5, to: 8, fromEdge: .low, toEdge: .high),
            ],
            labels: [
                .init(at: 3, anchor: .high, text: L("前高"), color: Theme.textSecondary),
                .init(at: 8, anchor: .high, text: L("创新高"), color: Theme.textPrimary),
            ],
            // 前一段柱子又高又密，后一段明显矮一截——面积比 < 1 就是背驰
            macdBars: [0.30, 0.72, 0.95, 0.80, 0.20, -0.35, 0.28, 0.42, 0.36],
            macdLabels: [
                .init(at: 2, anchor: .value(0.95), text: L("面积大"), color: Theme.up),
                .init(at: 7, anchor: .value(0.42), text: L("面积明显缩小 → 背驰"), color: Theme.down),
            ]
        )
    }

    /// MACD：柱、DIF/DEA，以及本 App 用来量化背驰的「面积比」。
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

    /// 三类买卖点：一买在背驰低点，二买不创新低，三买回踩不回中枢。
    private static var tradePoints: DiagramSpec {
        .fromPath(
            [0.72, 0.44, 0.16, 0.38, 0.24, 0.46, 0.38, 0.68, 0.56, 0.84],
            strokes: [
                .init(from: 2, to: 3, fromEdge: .low, toEdge: .high),
                .init(from: 3, to: 4, fromEdge: .high, toEdge: .low),
                .init(from: 4, to: 7, fromEdge: .low, toEdge: .high),
                .init(from: 7, to: 8, fromEdge: .high, toEdge: .low),
                .init(from: 8, to: 9, fromEdge: .low, toEdge: .high),
            ],
            pivots: [.init(from: 3, to: 6, top: 0.46, bottom: 0.24)],
            labels: [
                .init(at: 2, anchor: .value(0.08), text: L("一买"), color: Theme.up, above: false),
                .init(at: 4, anchor: .value(0.14), text: L("二买"), color: Theme.up, above: false),
                .init(at: 8, anchor: .value(0.46), text: L("三买"), color: Theme.up, above: false),
                .init(at: 5, anchor: .value(0.52), text: L("中枢"), color: Theme.pivotFill),
            ]
        )
    }

    /// 走势级别：两个小级别中枢，本身又构成一个更高级别的中枢。
    private static var level: DiagramSpec {
        .fromPath(
            [0.20, 0.36, 0.28, 0.40, 0.32, 0.56, 0.68, 0.58, 0.70, 0.60, 0.86],
            pivots: [
                .init(from: 1, to: 4, top: 0.42, bottom: 0.26, alpha: 0.14),
                .init(from: 6, to: 9, top: 0.72, bottom: 0.56, alpha: 0.14),
                .init(from: 1, to: 9, top: 0.78, bottom: 0.22, alpha: 0.10),
            ],
            labels: [
                .init(at: 2, anchor: .value(0.18), text: L("小级别"), color: Theme.textSecondary, above: false),
                .init(at: 8, anchor: .value(0.48), text: L("小级别"), color: Theme.textSecondary, above: false),
                .init(at: 5, anchor: .value(0.86), text: L("两者共同构成更高级别"), color: Theme.pivotFill),
            ]
        )
    }
}
