// Views/QueueDrawerView.swift
import SwiftUI

/// 当前播放队列：从右侧滑出的全高抽屉。
///
/// 用 NavigationStack + 自定义工具栏实现：原生 sheet 在 iOS 26 上的过渡是底部
/// 弹起的"卡片"，跟「点的是右侧按钮、看的是右侧抽屉」空间感对不上，用户左右
/// 行为不连贯。从右侧滑入、点击空白处或关闭按钮收起的体验更像音乐 App。
///
/// 列表行使用专门的按钮样式提供轻量按压反馈，滚动手势仍由 ScrollView 管理。
struct QueueDrawerView: View {
    let words: [VocabularyWord]
    let currentWordID: String?
    let onSelect: (VocabularyWord) -> Void
    let onDismiss: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isVisible = false
    @State private var scrollPosition: String?

    var body: some View {
        GeometryReader { geometry in
            let drawerWidth = min(geometry.size.width * 0.88, 380)

            ZStack(alignment: .trailing) {
                Button(action: dismissDrawer) {
                    Color.black.opacity(isVisible ? 0.45 : 0)
                        .ignoresSafeArea()
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭播放队列")

                drawer
                    .frame(width: drawerWidth)
                    .frame(maxHeight: .infinity, alignment: .top)
                    .background(Theme.surface)
                    .shadow(color: .black.opacity(0.5), radius: 20, x: -4, y: 0)
                    .offset(x: reduceMotion || isVisible ? 0 : drawerWidth)
                    .opacity(reduceMotion && !isVisible ? 0 : 1)
            }
            .ignoresSafeArea()
        }
        .preferredColorScheme(.dark)
        .task {
            // 等 fullScreenCover 的透明承载层先挂载，再执行自己的右侧入场动画。
            await Task.yield()
            withAnimation(presentationAnimation) {
                isVisible = true
            }
        }
        .accessibilityAction(.escape, dismissDrawer)
    }

    private var drawer: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if words.isEmpty {
                    ContentUnavailableView(
                        "这一组还没词",
                        systemImage: "music.note.list",
                        description: Text("先去拍照识别一些单词")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(Array(words.enumerated()), id: \.element.id) { index, word in
                                QueueDrawerRow(
                                    word: word,
                                    index: index,
                                    isCurrent: word.id == currentWordID
                                ) {
                                    select(word)
                                }
                                .id(word.id)
                            }
                        }
                        .scrollTargetLayout()
                        .padding(.vertical, 4)
                    }
                    .scrollIndicators(.hidden)
                    .scrollPosition(id: $scrollPosition, anchor: .center)
                    .task {
                        // LazyVStack 建立滚动目标后再绑定当前词，首次打开即可直接
                        // 落在正在播放/听写的行，而不是先显示列表开头。
                        await Task.yield()
                        scrollPosition = currentWordID
                    }
                    // 抽屉打开期间连播推进时，继续把新当前词带到视野中央。
                    .onChange(of: currentWordID) { _, newID in
                        guard let newID else { return }
                        withAnimation(.easeInOut(duration: 0.3)) {
                            scrollPosition = newID
                        }
                    }
                }
            }
            .navigationTitle("播放队列")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    HStack(spacing: 6) {
                        Text("\(words.count) 个")
                            .font(.caption)
                            .foregroundStyle(Theme.textSecondary)
                        if let currentID = currentWordID,
                           let idx = words.firstIndex(where: { $0.id == currentID }) {
                            Text("·")
                                .font(.caption)
                                .foregroundStyle(Theme.textSecondary)
                            Text("正在第 \(idx + 1) 个")
                                .font(.caption.weight(.medium))
                                .foregroundStyle(Theme.accent)
                        }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("关闭", action: dismissDrawer)
                        .tint(Theme.accent)
                }
            }
        }
    }

    private var presentationAnimation: Animation {
        reduceMotion ? .easeOut(duration: 0.15) : .easeOut(duration: 0.28)
    }

    private func dismissDrawer() {
        dismissDrawer(completion: onDismiss)
    }

    private func select(_ word: VocabularyWord) {
        dismissDrawer {
            onSelect(word)
        }
    }

    private func dismissDrawer(completion: @escaping () -> Void) {
        guard isVisible else { return }
        withAnimation(presentationAnimation) {
            isVisible = false
        } completion: {
            completion()
        }
    }
}

/// 列表行：组合「按压反馈 + 行高亮 + 当前词声波图标」三件事。
///
/// 用 `Button` 包整行做点按 + `.pressable` 提供缩放/高亮；同时按住 `.simultaneousGesture`
/// 让用户拖动滚动时不会被吞——之前只用纯 button 时偶发"我想上下滑但变成了点这一行"。
private struct QueueDrawerRow: View {
    let word: VocabularyWord
    let index: Int
    let isCurrent: Bool
    let onTap: () -> Void

    @State private var isPressed = false

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                Group {
                    if isCurrent {
                        Image(systemName: "speaker.wave.2.fill")
                            .foregroundStyle(Theme.accent)
                            .symbolEffect(.variableColor.iterative,
                                          isActive: isCurrent)
                    } else {
                        Text("\(index + 1)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(word.word)
                        .font(.body.weight(isCurrent ? .bold : .medium))
                        .foregroundStyle(isCurrent ? Theme.accent : Theme.textPrimary)
                    Text(word.definitionZh)
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                statusDot(word.status)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(rowBackground)
            .contentShape(.rect)
        }
        .buttonStyle(QueueRowButtonStyle(isPressed: $isPressed))
        .accessibilityLabel("\(word.word)，\(word.definitionZh)\(isCurrent ? "，正在播放" : "")")
        .accessibilityHint("双击从这个单词开始播放")
        .accessibilityAddTraits(isCurrent ? [.isSelected] : [])
    }

    /// 行底色：当前词用 surfaceAlt 高亮，按压时叠一层主题色 alpha。
    private var rowBackground: some View {
        (isCurrent ? Theme.surfaceAlt : Theme.surface)
            .overlay(isPressed ? Theme.accent.opacity(0.15) : .clear)
    }

    private func statusDot(_ status: String) -> some View {
        let color: Color = {
            switch status {
            case "known": return Theme.known
            case "fuzzy": return Theme.fuzzy
            default: return Theme.unknown
            }
        }()
        return Circle()
            .fill(color)
            .frame(width: 7, height: 7)
    }
}

/// 列表行的按钮样式：按下时缩一下 + 渐变到高亮色，比 .plain 反馈明确。
///
/// 用专门的 ButtonStyle 而不是 `.pressable`（项目里别处用的）：那个样式对单个
/// 图标按钮更合适，行内文字量大、容器宽，按比例缩看起来抖动明显。
private struct QueueRowButtonStyle: ButtonStyle {
    @Binding var isPressed: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
            .onChange(of: configuration.isPressed) { _, pressed in
                isPressed = pressed
            }
    }
}
