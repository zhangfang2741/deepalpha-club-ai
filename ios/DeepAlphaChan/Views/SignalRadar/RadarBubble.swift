import SwiftUI

/// 单个信号气泡：纯色实心（已确认的左上角打勾）+ 持续轻微漂浮 + 可按住拖拽（松手弹回原位）。
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
    /// 「待确认」候选：最后一笔还在走，不算买卖点——灰底 + 买卖方向色虚线边框 + 「待确认」标签，
    /// 不挂「新 / 共振」角标，与真实买卖点一眼区分。
    var isCandidate = false
    let onOpen: () -> Void

    /// 持续漂浮的竖向偏移（onAppear 后在 0 ↔ 负值间无限往复）。
    @State private var floatY: CGFloat = 0
    /// 拖拽偏移；松手后用弹簧动画归零。
    @State private var drag: CGSize = .zero
    /// 拖拽中放大一点，给「被拎起来」的反馈。
    @State private var dragging = false

    private var r: CGFloat { diameter / 2 }
    /// 已确认（所在笔已走完）：左上角打勾。宽松口径下每天多数气泡落在还没走完的最后一笔上、
    /// 是未确认的，所以只给少数已确认的做标记，不给多数未确认的挂标签（画面更干净）。
    private var isConfirmed: Bool { !isCandidate && signal.confirmed }

    var body: some View {
        content
            .frame(width: diameter, height: diameter)
            .scaleEffect(dragging ? 1.12 : 1.0)
            .offset(y: floatY)
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
                + (isCandidate ? " \(L("待确认，不算买卖点"))" : "")
                + (isCandidate ? "" : " \(isConfirmed ? L("已确认") : L("未确认"))")
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
            if isCandidate {
                Circle().fill(Theme.surfaceAlt)
                Circle().strokeBorder(color, style: StrokeStyle(lineWidth: 1.6, dash: [4, 3]))
            } else {
                Circle().fill(color)
            }

            VStack(spacing: 1) {
                Text(signal.symbol)
                    .font(Font(metrics.symbolFont))
                    .lineLimit(1)
                    .minimumScaleFactor(0.1)
                    .allowsTightening(true)
                    .foregroundColor(.white)
                // 有名称就显示（尺寸计算已保证两行放得下）；美股无中文名时名称为空，只显示代码
                if !signal.name.isEmpty {
                    Text(signal.name)
                        .font(Font(metrics.nameFont))
                        .foregroundColor(.white.opacity(0.92))
                        .lineLimit(1)
                        // 名称已按最小可读字号排版，再放不下就尾部截断，别压到看不清
                        .minimumScaleFactor(0.85)
                        .truncationMode(.tail)
                        .padding(.horizontal, 4)
                }
            }
            .frame(width: metrics.textWidth)
            .shadow(color: .black.opacity(0.4), radius: 2, y: 1)
        }
        .overlay(alignment: .bottom) {
            if isCandidate {
                Text(L("待确认"))
                    .font(.system(size: max(8, min(11, r * 0.2)), weight: .semibold))
                    .foregroundColor(Theme.textSecondary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1)
                    .background(Theme.background, in: Capsule())
                    .overlay(Capsule().stroke(Theme.textSecondary.opacity(0.6), lineWidth: 0.8))
                    .offset(y: 6)
            }
        }
        .overlay(alignment: .topTrailing) {
            // "新"改放气泡外面右上角：挤在气泡内部会跟代码/名称文字抢地方。
            if isNew && !isCandidate {
                Text(L("新"))
                    .font(.system(size: max(8, min(12, r * 0.22)), weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Theme.segment)
                    .clipShape(Capsule())
                    .offset(x: 4, y: -4)
            }
        }
        .overlay(alignment: .topLeading) {
            // 已确认：白色对勾 + 深色描边小圆，红 / 绿气泡上都清楚，不与买卖方向色混淆。
            if isConfirmed {
                let side = max(14, min(20, r * 0.36))
                Image(systemName: "checkmark")
                    .font(.system(size: side * 0.55, weight: .heavy))
                    .foregroundColor(.white)
                    .frame(width: side, height: side)
                    .background(Theme.background, in: Circle())
                    .overlay(Circle().stroke(.white.opacity(0.85), lineWidth: 1))
                    .offset(x: -3, y: -3)
                    .accessibilityHidden(true)
            }
        }
        .overlay(alignment: .bottomLeading) {
            // 日线定方向 × 30 分钟找买卖点同向（共振），只在最新交易日的入榜气泡上出现。
            if signal.isSubLevelResonance && !isCandidate {
                Text(L("共振"))
                    .font(.system(size: max(8, min(12, r * 0.22)), weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1.5)
                    .background(Theme.accent)
                    .clipShape(Capsule())
                    .offset(x: -4, y: 4)
            }
        }
    }
}
