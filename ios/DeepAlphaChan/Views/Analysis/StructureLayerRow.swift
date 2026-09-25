import SwiftUI

/// 结构名称沿用 K 线图层颜色；买卖点类别不混用代表方向的红绿。
struct StructureLayerRow: View {
    let layer: StructureLayer

    private var term: String {
        switch layer.layer {
        case "stroke": return "笔"
        case "segment": return "线段"
        case "pivot": return "中枢"
        case "signal": return "买卖点"
        default: return layer.label
        }
    }

    private var color: Color {
        switch layer.layer {
        case "stroke": return Theme.stroke
        case "segment": return Theme.segment
        case "pivot": return Theme.pivotFill
        default: return Theme.textSecondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            AnalysisTermLink(term: term, color: color)
            Text(HeadlineHighlighter.highlight(layer.title))
                .font(.subheadline.bold())
                .foregroundStyle(Theme.textPrimary)
            Text(HeadlineHighlighter.highlight(layer.detail))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textSecondary)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
    }
}
