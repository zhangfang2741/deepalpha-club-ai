import SwiftUI

/// 听写判定后的决策卡：右滑接受系统结论，左滑回到当前词重新听写。
///
/// 评分在右滑前只存在于本地状态中；本视图只负责交互和展示，真正的提交与重播由
/// ReviewViewModel 处理。VoiceOver 用户通过两个自定义操作获得等价能力。
struct DictationResultCard: View {
    let word: VocabularyWord
    let typed: String
    let resultLabel: String
    let resultColor: Color
    let resultSurfaceColor: Color
    let showsTypedInput: Bool
    let isSubmitting: Bool
    let onOpenDetail: () -> Void
    let onAccept: () -> Void
    let onRetry: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dragOffset: Double = 0
    @State private var crossedThreshold = false
    @State private var feedbackTrigger = 0
    @State private var commitFeedbackTrigger = 0
    @State private var actionInFlight = false
    @State private var committedDirection = 0

    private static let swipeThreshold: Double = 88
    private static let flickThreshold: Double = 132
    private static let minimumFlickDistance: Double = 36
    private static let dismissOffset: Double = 560

    private var dragProgress: Double {
        min(abs(dragOffset) / Self.swipeThreshold, 1)
    }

    private var activeDirection: Int {
        if committedDirection != 0 { return committedDirection }
        if dragOffset < -8 { return -1 }
        if dragOffset > 8 { return 1 }
        return 0
    }

    var body: some View {
        ZStack {
            actionBackdrop

            VStack(spacing: 14) {
                Text("系统判断 · \(resultLabel)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 7)
                    .background(resultSurfaceColor)
                    .clipShape(.capsule)

                HStack {
                    Text(word.word)
                        .font(.largeTitle.bold())
                        .foregroundStyle(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/")
                    .foregroundStyle(Theme.textSecondary)

                if showsTypedInput {
                    Text("你写的：\(typed.trimmingCharacters(in: .whitespacesAndNewlines))")
                        .font(.subheadline)
                        .foregroundStyle(resultColor)
                }

                Text("\(word.partOfSpeech) \(word.definitionZh)")
                    .font(.title3)
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)

                if isSubmitting {
                    HStack(spacing: 8) {
                        ProgressView().tint(resultColor)
                        Text("正在保存并进入下一个…")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Theme.textSecondary)
                }
            }
            .padding()
            .frame(maxWidth: .infinity)
            .frame(minHeight: 250)
            .background(Theme.surface)
            .overlay {
                if !isSubmitting {
                    DictationSwipeInstructions(resultColor: resultColor)
                        .allowsHitTesting(false)
                }
            }
            .offset(x: dragOffset)
            .shadow(
                color: activeDirection == 0 ? .black.opacity(0.28) : .black.opacity(0.48),
                radius: activeDirection == 0 ? 8 : 15,
                x: 0,
                y: activeDirection == 0 ? 3 : 7
            )
        }
        .background(backdropColor)
        .clipShape(.rect(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(activeDirection == 0 ? Theme.border : activeColor, lineWidth: 2)
        }
        .contentShape(.rect)
        .simultaneousGesture(swipeGesture)
        // DragGesture 设有 14pt 的最小距离，因此轻点会进入详情；一旦形成横向
        // 拖动，TapGesture 会自动失败，不会在松手时误打开详情页。
        .onTapGesture(perform: onOpenDetail)
        .sensoryFeedback(.impact(weight: .heavy, intensity: 1), trigger: feedbackTrigger)
        .sensoryFeedback(.success, trigger: commitFeedbackTrigger)
        .onChange(of: isSubmitting) { wasSubmitting, submitting in
            // 右滑已退出、但服务端保存失败时，结果相位不会切走。此时把卡片弹回
            // 中央，让用户能看到错误并再次右滑提交。
            guard wasSubmitting, !submitting, actionInFlight else { return }
            resetCardPosition()
        }
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("双击查看单词详情，右滑接受系统判断并进入下一个，左滑重新听写当前单词")
        .accessibilityAction { onOpenDetail() }
        .accessibilityAction(named: "接受系统判断并进入下一个") {
            guard !isSubmitting else { return }
            onAccept()
        }
        .accessibilityAction(named: "重新听写当前单词") {
            guard !isSubmitting else { return }
            onRetry()
        }
    }

    private var activeColor: Color {
        activeDirection == -1 ? Theme.accent : resultColor
    }

    private var backdropColor: Color {
        switch activeDirection {
        case -1: return Theme.dictationRetrySurface
        case 1: return resultSurfaceColor
        default: return Theme.surfaceAlt
        }
    }

    @ViewBuilder
    private var actionBackdrop: some View {
        if actionInFlight, committedDirection == 1 {
            DictationAcceptedState(resultLabel: resultLabel)
        } else {
            HStack {
                Label(resultLabel, systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.white)
                    .opacity(activeDirection == 1 ? max(0.45, dragProgress) : 0)
                    .scaleEffect(activeDirection == 1 ? 0.9 + dragProgress * 0.1 : 0.9)

                Spacer()

                Label("重来", systemImage: "arrow.counterclockwise.circle.fill")
                    .foregroundStyle(.white)
                    .opacity(activeDirection == -1 ? max(0.45, dragProgress) : 0)
                    .scaleEffect(activeDirection == -1 ? 0.9 + dragProgress * 0.1 : 0.9)
            }
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 22)
        }
    }

    private var swipeGesture: some Gesture {
        DragGesture(minimumDistance: 14)
            .onChanged { value in
                guard !isSubmitting, !actionInFlight else { return }
                let horizontal = Double(value.translation.width)
                let vertical = Double(value.translation.height)
                guard abs(horizontal) > abs(vertical) else { return }

                // 拖动阶段不附加动画，保证卡片严格跟手；超过确认阈值后增加一点
                // 阻尼，既保留继续拖动的空间，也避免卡片轻易飞出屏幕。
                let sign = horizontal < 0 ? -1.0 : 1.0
                let distance = abs(horizontal)
                let resistedDistance = distance <= Self.swipeThreshold
                    ? distance
                    : Self.swipeThreshold + (distance - Self.swipeThreshold) * 0.42
                dragOffset = sign * resistedDistance

                let isNowAcrossThreshold = distance >= Self.swipeThreshold
                if isNowAcrossThreshold, !crossedThreshold {
                    feedbackTrigger += 1
                }
                crossedThreshold = isNowAcrossThreshold
            }
            .onEnded { value in
                guard !isSubmitting, !actionInFlight else { return }
                let horizontal = Double(value.translation.width)
                let vertical = Double(value.translation.height)
                let projected = Double(value.predictedEndTranslation.width)
                crossedThreshold = false
                guard abs(horizontal) > abs(vertical) else {
                    resetCardPosition()
                    return
                }

                let passedDistance = abs(horizontal) >= Self.swipeThreshold
                let deliberateFlick = abs(horizontal) >= Self.minimumFlickDistance
                    && abs(projected) >= Self.flickThreshold
                guard passedDistance || deliberateFlick else {
                    resetCardPosition()
                    return
                }

                let direction = (projected == 0 ? horizontal : projected) < 0 ? -1 : 1
                completeSwipe(direction: direction)
            }
    }

    private func completeSwipe(direction: Int) {
        committedDirection = direction
        actionInFlight = true
        commitFeedbackTrigger += 1

        guard !reduceMotion else {
            dragOffset = 0
            performAction(direction: direction)
            return
        }

        // 只做单向水平退出，不旋转、不缩放，也不使用带回弹的动画。
        withAnimation(.smooth(duration: 0.22)) {
            dragOffset = Double(direction) * Self.dismissOffset
        } completion: {
            performAction(direction: direction)
        }
    }

    private func performAction(direction: Int) {
        if direction > 0 {
            onAccept()
        } else {
            onRetry()
        }
    }

    private func resetCardPosition() {
        committedDirection = 0
        actionInFlight = false
        // 未达到阈值时匀顺回中，不产生左右过冲。
        withAnimation(.easeOut(duration: reduceMotion ? 0.1 : 0.18)) {
            dragOffset = 0
        }
    }
}
