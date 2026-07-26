// Views/Components/ReviewCardFlipPrototypes.swift
//
// 阶段3 动效探索：ReviewCardView 翻卡动效的 3 个命名方案，纯 #Preview + mock 数据，
// 不依赖后端/账号数据。在 Xcode Canvas 里点开每个 Preview，点卡片本身就能看到
// 动效实际播放效果。选定方案后会移植进 ReviewCardView.swift，这个文件随后会删除。
import SwiftUI

private let mockWord = VocabularyWord(
    id: "preview", word: "ephemeral", phoneticIpa: "ɪˈfemərəl", partOfSpeech: "adj.",
    definitionZh: "短暂的，转瞬即逝的", etymology: "", exampleSentence: "", status: "new",
    repetitionCount: 0, easinessFactor: 2.5, intervalDays: 1,
    nextReviewAt: "", lastReviewedAt: nil, createdAt: ""
)

private func ratingRow(visible: Bool) -> some View {
    HStack(spacing: 12) {
        ForEach([("😵 不认识", Theme.unknown), ("😐 模糊", Theme.fuzzy), ("😊 认识", Theme.known)], id: \.0) { label, color in
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.2))
                .foregroundStyle(color)
                .clipShape(.rect(cornerRadius: 10))
        }
    }
    .padding(.horizontal)
    .opacity(visible ? 1 : 0)
}

// MARK: - 方案 A：淡入淡出（改动最小，延续现有交叉淡出习惯）

private struct FadeFlipCard: View {
    let word: VocabularyWord
    @State private var isFlipped = false

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 16) {
                HStack {
                    Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)

                if isFlipped {
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.title3)
                        .foregroundStyle(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
                        .transition(.opacity.combined(with: .scale(scale: 0.95)))
                } else {
                    Text("点击翻转看释义")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 220)
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 16))
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.25)) { isFlipped.toggle() }
            }
            .padding(.horizontal)

            ratingRow(visible: isFlipped)
        }
    }
}

#Preview("翻卡动效 A - 淡入淡出") {
    ZStack { Theme.background.ignoresSafeArea(); FadeFlipCard(word: mockWord) }
}

// MARK: - 方案 B：3D 翻转（视觉上真的"翻卡片"，最贴合"翻转"这个说法）

private struct Flip3DCard: View {
    let word: VocabularyWord
    @State private var isFlipped = false

    var body: some View {
        VStack(spacing: 24) {
            ZStack {
                face(showBack: false)
                    .opacity(isFlipped ? 0 : 1)
                    .rotation3DEffect(.degrees(isFlipped ? 90 : 0), axis: (x: 0, y: 1, z: 0))
                face(showBack: true)
                    .opacity(isFlipped ? 1 : 0)
                    .rotation3DEffect(.degrees(isFlipped ? 0 : -90), axis: (x: 0, y: 1, z: 0))
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 220)
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 16))
            .onTapGesture {
                withAnimation(.spring(duration: 0.45, bounce: 0.2)) { isFlipped.toggle() }
            }
            .padding(.horizontal)

            ratingRow(visible: isFlipped)
        }
    }

    private func face(showBack: Bool) -> some View {
        VStack(spacing: 16) {
            if !showBack {
                HStack {
                    Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)
                Text("点击翻转看释义").font(.caption).foregroundStyle(Theme.textSecondary)
            } else {
                Text("\(word.partOfSpeech) \(word.definitionZh)")
                    .font(.title3)
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)
            }
        }
    }
}

#Preview("翻卡动效 B - 3D 翻转") {
    ZStack { Theme.background.ignoresSafeArea(); Flip3DCard(word: mockWord) }
}

// MARK: - 方案 C：缩放弹跳（释义带一点回弹，强调"揭晓"的瞬间）

private struct ScaleBounceCard: View {
    let word: VocabularyWord
    @State private var isFlipped = false

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 16) {
                HStack {
                    Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)

                if isFlipped {
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.title3)
                        .foregroundStyle(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
                        .transition(.scale(scale: 0.8).combined(with: .opacity))
                } else {
                    Text("点击翻转看释义")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 220)
            .background(Theme.surface)
            .clipShape(.rect(cornerRadius: 16))
            .onTapGesture {
                withAnimation(.spring(duration: 0.4, bounce: 0.5)) { isFlipped.toggle() }
            }
            .padding(.horizontal)

            ratingRow(visible: isFlipped)
        }
    }
}

#Preview("翻卡动效 C - 缩放弹跳") {
    ZStack { Theme.background.ignoresSafeArea(); ScaleBounceCard(word: mockWord) }
}
