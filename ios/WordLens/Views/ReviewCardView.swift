// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.queue.isEmpty {
                    ContentUnavailableView(
                        "今天没有待复习的单词",
                        systemImage: "checkmark.circle",
                        description: Text("去拍照识别一些新单词吧")
                    )
                } else if viewModel.isFinished {
                    ContentUnavailableView(
                        "今日复习完成 🎉",
                        systemImage: "star.fill",
                        description: Text("共复习了 \(viewModel.totalCount) 个单词")
                    )
                } else if let word = viewModel.currentWord {
                    cardContent(word)
                }
            }
            .navigationTitle("复习")
            .navigationBarTitleDisplayMode(.inline)
            .task { await viewModel.loadQueue() }
            .refreshable { await viewModel.loadQueue() }
        }
    }

    private func cardContent(_ word: VocabularyWord) -> some View {
        VStack(spacing: 24) {
            Text("\(viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)

            Spacer()

            VStack(spacing: 16) {
                HStack {
                    Text(word.word).font(.largeTitle.bold()).foregroundStyle(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundStyle(Theme.textSecondary)

                if viewModel.isFlipped {
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.title3)
                        .foregroundStyle(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
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
            .onTapGesture { viewModel.flip() }
            // onTapGesture 本身不会被 VoiceOver 当成可激活元素，加上 button 语义 +
            // 明确的 label/hint，双击手势才能触发翻卡片。
            .accessibilityAddTraits(.isButton)
            .accessibilityLabel(word.word)
            .accessibilityHint(viewModel.isFlipped ? "已展开释义，双击收起" : "双击查看释义")
            .padding(.horizontal)

            Spacer()

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
            }

            if viewModel.isFlipped {
                HStack(spacing: 12) {
                    ratingButton("😵 不认识", Theme.unknown, .unknown)
                    ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                    ratingButton("😊 认识", Theme.known, .known)
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
            }
        }
    }

    private func ratingButton(_ label: String, _ color: Color, _ rating: ReviewRating) -> some View {
        Button {
            Task { await viewModel.submit(rating) }
        } label: {
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.2))
                .foregroundStyle(color)
                .clipShape(.rect(cornerRadius: 10))
        }
        .disabled(viewModel.isSubmitting)
    }
}
