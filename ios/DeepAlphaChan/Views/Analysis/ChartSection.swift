import SwiftUI

/// 图层开关 + K 线图 + 图例。
struct ChartSection: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    /// 点全屏。编排（先转屏再呈现）在调用方，这里只管发信号。
    let onFullscreen: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            // 全屏按钮放在图层开关这一行的最右侧，不叠在图上。
            // 试过压在图表右下角和右上角：一个盖住 X 轴日期，一个盖住 Y 轴顶部刻度。
            // 图表四角都有刻度，本来就没有可供悬浮的空白区。
            HStack(spacing: 8) {
                LayerToggles(vm: vm)
                fullscreenButton
            }

            ChanChartView(analysis: analysis, vm: vm)

            ChartLegend()
        }
    }

    private var fullscreenButton: some View {
        Button(action: onFullscreen) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Theme.accent)
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(Theme.surfaceAlt)
                .clipShape(Capsule())
        }
        // 纯图标按钮必须给 label，否则 VoiceOver 只会念出「按钮」
        .accessibilityLabel(L("全屏查看图表"))
        .accessibilityHint(L("横屏显示，可看到更多 K 线"))
    }
}

/// 图层开关。全屏页也要用，所以独立出来。
struct LayerToggles: View {
    @ObservedObject var vm: ChanViewModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip(L("分型"), isOn: $vm.showFractals)
                chip(L("笔"), isOn: $vm.showStrokes)
                chip(L("线段"), isOn: $vm.showSegments)
                chip(L("中枢"), isOn: $vm.showPivots)
                chip(L("买卖点"), isOn: $vm.showSignals)
            }
            .padding(.horizontal, 2)
        }
    }

    private func chip(_ title: String, isOn: Binding<Bool>) -> some View {
        Button { isOn.wrappedValue.toggle() } label: {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(isOn.wrappedValue ? Theme.accent.opacity(0.2) : Theme.surfaceAlt)
                .foregroundColor(isOn.wrappedValue ? Theme.accent : Theme.textSecondary)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(isOn.wrappedValue ? Theme.accent.opacity(0.5) : .clear, lineWidth: 1))
        }
    }
}

/// 颜色图例。每个术语都能点开对应词条——图例本来就是给看不懂的人准备的，
/// 让它只显示颜色而不能解释含义是浪费。
///
/// 两个刻意的选择：
/// - 术语不加下划线。中文在 caption2 字号下虚下划线会贴着甚至穿过字身，看起来
///   像删除线。改用「可点的是白字、纯说明是灰字」来区分。
/// - 「点术语看解释」这行提示不放进横向滚动条里。放进去会被截断成半个词，
///   而且要滑到最右才看得见，起不到提示作用。
struct ChartLegend: View {
    var body: some View {
        VStack(spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                // 图例形状与图上一致：笔/线段=实线，中枢=方框，分型=圆点，未确认=灰色虚线
                HStack(spacing: 14) {
                    labeled("笔") { lineGlyph(Theme.stroke, width: 2) }
                    labeled("线段") { lineGlyph(Theme.segment, width: 2.6) }
                    labeled("中枢") { boxGlyph(Theme.pivotFill) }
                    labeled("顶分型") { dotGlyph(Theme.topFractal) }
                    labeled("底分型") { dotGlyph(Theme.bottomFractal) }
                    labeled("未确认") { dashGlyph() }
                }
                .padding(.horizontal, 4)
            }

            HStack(spacing: 3) {
                Image(systemName: "hand.tap").font(.system(size: 9))
                Text(L("点术语可查看解释")).font(.caption2)
            }
            .foregroundColor(Theme.accent.opacity(0.75))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4)
        }
    }

    /// 一条图例项：图形 + 本地化术语。可点的（有词条）显示白字并跳词条，否则灰字。
    private func labeled<G: View>(_ term: String, @ViewBuilder glyph: () -> G) -> some View {
        GlossaryLink(term: term) {
            HStack(spacing: 4) {
                glyph()
                Text(L(term))
                    .font(.caption2)
                    .foregroundColor(GlossaryIndex.hasEntry(for: term)
                                     ? Theme.textPrimary : Theme.textSecondary)
            }
        }
    }

    // MARK: 图例图形

    /// 实线（笔 / 线段）
    private func lineGlyph(_ color: Color, width: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: width / 2)
            .fill(color)
            .frame(width: 14, height: width)
    }

    /// 方框（中枢）：描边 + 淡填充，对应图上的中枢矩形
    private func boxGlyph(_ color: Color) -> some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(color.opacity(0.18))
            .overlay(RoundedRectangle(cornerRadius: 2).stroke(color, lineWidth: 1))
            .frame(width: 14, height: 10)
    }

    /// 圆点（顶 / 底分型），对应图上的分型标记
    private func dotGlyph(_ color: Color) -> some View {
        Circle().fill(color).frame(width: 7, height: 7)
    }

    /// 灰色虚线（未确认），对应图上未确认结构的虚线画法
    private func dashGlyph() -> some View {
        Canvas { ctx, size in
            var p = Path()
            p.move(to: CGPoint(x: 0, y: size.height / 2))
            p.addLine(to: CGPoint(x: size.width, y: size.height / 2))
            ctx.stroke(p, with: .color(Theme.textSecondary),
                       style: StrokeStyle(lineWidth: 1.5, dash: [3, 2]))
        }
        .frame(width: 16, height: 4)
    }
}
