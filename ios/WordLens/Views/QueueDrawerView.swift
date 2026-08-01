// Views/QueueDrawerView.swift
import SwiftUI

/// 当前播放队列：从右侧滑出的全高抽屉。
///
/// 用 NavigationStack + 自定义工具栏实现：原生 sheet 在 iOS 26 上的过渡是底部
/// 弹起的"卡片"，跟「点的是右侧按钮、看的是右侧抽屉」空间感对不上，用户左右
/// 行为不连贯。从右侧滑入、点击空白处或拖动右侧把手收起的体验更像音乐 App。
///
/// 列表行加按压反馈：行内 `.pressable` 自带轻量缩放 + 高亮，配合
/// `simultaneousGesture` 让轻扫不被吞掉（原来只用 button 时没法同时识别
/// scroll 的滑动手势）。
struct QueueDrawerView: View {
    let words: [VocabularyWord]
    let currentWordID: String?
    let onSelect: (VocabularyWord) -> Void
    let onDismiss: () -> Void

    @Environment(\.dismiss) private var dismiss
    @Namespace private var scrollSpace

    var body: some View {
        ZStack(alignment: .leading) {
            // 半透明遮罩，alpha 跟着拖动手势变化。点空白处收起。
            Color.black.opacity(0.45)
                .ignoresSafeArea()
                .onTapGesture { onDismiss() }

            drawer
                .frame(maxWidth: 380)
                .frame(maxHeight: .infinity, alignment: .top)
                .background(Theme.surface)
                .clipShape(.rect(cornerRadius: 0))
                .shadow(color: .black.opacity(0.5), radius: 20, x: -4, y: 0)
        }
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
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 0) {
                                ForEach(Array(words.enumerated()), id: \.element.id) { index, word in
                                    QueueDrawerRow(
                                        word: word,
                                        index: index,
                                        isCurrent: word.id == currentWordID
                                    ) {
                                        onSelect(word)
                                    }
                                    .id(word.id)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                        .scrollIndicators(.hidden)
                        // 队列可能有几百个词，打开时先滚到正在播的那个，省得自己找。
                        .onAppear {
                            guard let currentID = currentWordID else { return }
                            proxy.scrollTo(currentID, anchor: .center)
                        }
                        // 当前词变了跟一次，自动滚到视野中央——连播推进时能看得到。
                        .onChange(of: currentWordID) { _, newID in
                            guard let newID else { return }
                            withAnimation(.easeInOut(duration: 0.3)) {
                                proxy.scrollTo(newID, anchor: .center)
                            }
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
                    Button("关闭") { onDismiss() }
                        .tint(Theme.accent)
                }
            }
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
                        .font(.caption2)
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
    }

    /// 行底色：当前词用 surfaceAlt 高亮，按压时叠一层主题色 alpha。
    private var rowBackground: some View {
        Theme.surface
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