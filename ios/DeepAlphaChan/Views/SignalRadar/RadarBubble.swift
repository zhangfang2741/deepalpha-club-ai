import SwiftUI

/// 单个信号气泡：纯色实心 + 持续轻微漂浮 + 可按住拖拽（松手弹回原位）。
struct RadarBubble: View {
    let signal: RadarSignal
    let metrics: RadarBubbleMetrics
    private var diameter: CGFloat { metrics.diameter }
    let baseX: CGFloat
    let baseY: CGFloat
    let phase: Double
    let color: Color
    /// 信号是不是查看这天当天新出现的（而非从更早的日子延续到现在）。
    let isNew: Bool
    let onOpen: () -> Void

    /// 持续漂浮的竖向偏移（onAppear 后在 0 ↔ 负值间无限往复）。
    @State private var floatY: CGFloat = 0
    /// 拖拽偏移；松手后用弹簧动画归零。
    @State private var drag: CGSize = .zero
    /// 拖拽中放大一点，给「被拎起来」的反馈。
    @State private var dragging = false

    private var r: CGFloat { diameter / 2 }

    var body: some View {
        content
            .frame(width: diameter, height: diameter)
            .scaleEffect(dragging ? 1.12 : 1.0)
            .offset(y: isNew ? 0 : floatY)
            .offset(drag)
            .shadow(color: .black.opacity(dragging ? 0.5 : 0.35),
                    radius: dragging ? 12 : 6, y: dragging ? 8 : 3)
            .contentShape(Circle())
            .gesture(
                DragGesture()
                    .onChanged { value in
                        if !dragging { withAnimation(.easeOut(duration: 0.15)) { dragging = true } }
                        drag = value.translation
                    }
                    .onEnded { _ in
                        withAnimation(.spring(response: 0.45, dampingFraction: 0.55)) {
                            drag = .zero
                        }
                        withAnimation(.easeOut(duration: 0.2)) { dragging = false }
                    }
            )
            .onTapGesture { onOpen() }
            .position(x: baseX, y: baseY)
            .accessibilityElement()
            .accessibilityLabel(
                "\(signal.symbol) \(signal.name) \(signal.isBuy ? L("买点") : L("卖点"))"
                + (isNew ? " \(L("所选日期当天新增"))" : "")
                + (signal.isSubLevelResonance ? " \(L("日线与30分钟共振"))" : "")
            )
            .accessibilityAddTraits(.isButton)
            .onAppear {
                floatY = -6
                withAnimation(
                    .easeInOut(duration: Double.random(in: 2.2...3.4))
                        .repeatForever(autoreverses: true)
                        .delay(phase * 0.2)
                ) {
                    floatY = 6
                }
            }
    }

    private var content: some View {
        ZStack {
            // 纯实色气泡；未确认的信号额外描一圈虚线边框——跟图表页「虚线=未确认」
            // 同一套语言，确认的信号维持无描边的纯实色（多数信号都是已确认的，
            // 不想让所有气泡都套上边框，那样反而弱化了「未确认」这个特殊标记）。
            Circle().fill(color)
            if !signal.confirmed {
                Circle().stroke(style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    .foregroundColor(.white.opacity(0.85))
            }

            VStack(spacing: 1) {
                Text(signal.symbol)
                    .font(Font(metrics.symbolFont))
                    .lineLimit(1)
                    .minimumScaleFactor(0.1)
                    .allowsTightening(true)
                    .foregroundColor(.white)
                Text(signal.name)
                    .font(Font(metrics.nameFont))
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(1)
                    .padding(.horizontal, 4)
            }
            .frame(width: metrics.textWidth)
            .shadow(color: .black.opacity(0.4), radius: 2, y: 1)
        }
        .overlay(alignment: .topTrailing) {
            // "新"改放气泡外面右上角：挤在气泡内部会跟代码/名称文字抢地方。
            if isNew {
                Text(L("新"))
                    .font(.system(size: max(8, min(12, r * 0.22)), weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Theme.segment)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(Theme.background, lineWidth: 1))
                    .offset(x: 4, y: -4)
            }
        }
        .overlay(alignment: .bottomLeading) {
            // 日线定方向 × 30 分钟找买卖点同向（共振），只在最新交易日的入榜气泡上出现。
            if signal.isSubLevelResonance {
                Text(L("共振"))
                    .font(.system(size: max(8, min(12, r * 0.22)), weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Theme.accent)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(Theme.background, lineWidth: 1))
                    .offset(x: -4, y: 4)
            }
        }
    }
}
