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
    @State private var cardWidth: Double = 0

    private static let dismissOffset: Double = 560

    /// 要推过卡片一半的宽度才算数。原来是固定 88pt——在 6.1 吋屏上还不到卡片宽度的
    /// 四分之一，手指随便带一下就把这一题判掉了，重来/继续都不该这么轻。
    private var swipeThreshold: Double {
        max(120, cardWidth * 0.5)
    }

    /// 甩动的快捷路径：允许没推到一半就松手，但必须是明确的一甩——既要有真实位移，
    /// 惯性预测的落点也要远远越过阈值。原来只要 36pt 位移就可能触发，太容易误判。
    private var minimumFlickDistance: Double { swipeThreshold * 0.55 }
    private var flickThreshold: Double { swipeThreshold * 1.6 }

    private var dragProgress: Double {
        min(abs(dragOffset) / swipeThreshold, 1)
    }

    private var activeDirection: Int {
        if committedDirection != 0 { return committedDirection }
        if dragOffset < -8 { return -1 }
        if dragOffset > 8 { return 1 }
        return 0
    }

    var body: some View {
        VStack(spacing: 12) {
            // 判定结论和「你写的」都挂在卡片外面、压在卡片上方。它们曾经在卡片内部，
            // 把整段内容往上顶，正好把释义推到垂直中线，和悬浮在那里的滑动引导带叠
            // 在一起。移出去之后卡片内容回到原来的高度，引导带不会再撞上任何东西。
            verdictBanner

            card
        }
    }

    private var card: some View {
        ZStack {
            actionBackdrop

            // 间距按「接近性」分组，而不是所有元素等距：单词和音标是同一个单位
            // （这个词长什么样、怎么读），释义是另一个单位（它是什么意思）。组内
            // 8pt、组间 28pt，约 1:3.5——差距要足够大，眼睛才会自动把它们读成两块，
            // 而不是三行等距的清单。
            VStack(spacing: 28) {
                VStack(spacing: 8) {
                    Text(word.word)
                        .font(.largeTitle.bold())
                        .foregroundStyle(Theme.textPrimary)

                    // 小喇叭跟音标走：它读的是「怎么念」，和音标是同一件事；
                    // 挂在单词后面会把标题那行拉偏，单词也就不居中了。
                    HStack(spacing: 8) {
                        Text("/\(word.phoneticIpa)/")
                            .foregroundStyle(Theme.textSecondary)
                        PronounceButton(word: word.word)
                    }
                }

                VStack(spacing: 12) {
                    typedLine

                    // 释义用 body：比单词小一大截，和音标同号但用主色区分——大小拉开
                    // 层级，颜色区分角色，比两者都靠字号硬顶要稳。
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.body)
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
            }
            // 上下留白也一并放大：内容之间松了，四周还挤着的话整张卡反而更局促。
            .padding(.vertical, 26)
            .padding(.horizontal, 18)
            .frame(maxWidth: .infinity)
            .frame(minHeight: 250)
            .background(Theme.surface)
            .overlay {
                if !isSubmitting {
                    DictationSwipeInstructions()
                        .allowsHitTesting(false)
                }
            }
            .offset(x: dragOffset)
            // 阴影也跟着拖动进度连续变化，不再在越过 8pt 的瞬间跳一下。
            .shadow(
                color: .black.opacity(0.28 + 0.2 * dragProgress),
                radius: 8 + 7 * dragProgress,
                x: 0,
                y: 3 + 4 * dragProgress
            )
        }
        .background(backdrop)
        // 阈值按卡片实际宽度算，所以要把宽度量出来（不同机型、横竖屏都不一样）。
        .background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { cardWidth = proxy.size.width }
                    .onChange(of: proxy.size.width) { _, width in cardWidth = width }
            }
        }
        .clipShape(.rect(cornerRadius: 16))
        // 边框保持中性灰：滑动方向靠背景渐变表达，描边再上色就成了双重强调。
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(Theme.border, lineWidth: 1)
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

    /// 结论 +「你写的」，独立挂在卡片上方，不占卡片内部空间。
    ///
    /// 结论用约定的状态色：没记住红、模糊黄、记住了绿。判对时不显示「你写的」，
    /// 这一块就只剩一行结论。
    /// 卡片上方的结论。统一用主题蓝、常规字重、和释义同字号：它是一句陈述，
    /// 不是警报——三档状态色 + 加粗 + 大字号叠在一起，比卡片里的单词还抢眼。
    private var verdictBanner: some View {
        Text(resultLabel)
            .font(.body)
            .foregroundStyle(Theme.accent)
    }

    /// 「你写的」贴在释义正上方。
    @ViewBuilder
    private var typedLine: some View {
        if showsTypedInput {
            // 基线对齐：标签和内容字号不同，用 center 对齐会一高一低，落在同一条
            // 基线上才像一句话。
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                // 「你写的」是标签，压小半号的次级灰；写错的那版才是主角。
                Text("你写的：")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                Text(typed.trimmingCharacters(in: .whitespacesAndNewlines))
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(Theme.accent)
            }
            .lineLimit(1)
            // 超长的词宁可缩一点，也不要挤断成两行破坏这一行的结构。
            .minimumScaleFactor(0.7)
        }
    }

    /// 卡片底下露出来的那层。不再随滑动方向上色——方向已经由两侧的动作标签
    /// （继续 / 再来一次）和它们跟手的浓度表达，底色再变一次是重复。
    private var backdrop: some View {
        Theme.surfaceAlt
    }

    @ViewBuilder
    private var actionBackdrop: some View {
        if actionInFlight, committedDirection == 1 {
            DictationAcceptedState(resultLabel: resultLabel)
        } else {
            HStack {
                // 提示语的浓度跟着底色一起走：底色淡的时候文字也别抢戏。
                // 用 forward 而不是 right：它在从右到左的语言环境下会自动镜像。
                Label("继续", systemImage: "arrow.forward.circle.fill")
                    .foregroundStyle(.white)
                    .opacity(activeDirection == 1 ? dragProgress : 0)
                    .scaleEffect(activeDirection == 1 ? 0.9 + dragProgress * 0.1 : 0.9)

                Spacer()

                Label("再来一次", systemImage: "arrow.counterclockwise.circle.fill")
                    .foregroundStyle(.white)
                    .opacity(activeDirection == -1 ? dragProgress : 0)
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
                let resistedDistance = distance <= swipeThreshold
                    ? distance
                    : swipeThreshold + (distance - swipeThreshold) * 0.42
                dragOffset = sign * resistedDistance

                let isNowAcrossThreshold = distance >= swipeThreshold
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

                let passedDistance = abs(horizontal) >= swipeThreshold
                let deliberateFlick = abs(horizontal) >= minimumFlickDistance
                    && abs(projected) >= flickThreshold
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
