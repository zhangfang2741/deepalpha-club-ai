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
                    emptyState(title: "今天没有待复习的单词", subtitle: "去拍照识别一些新单词吧")
                } else if viewModel.isFinished {
                    emptyState(title: "今日复习完成 🎉", subtitle: "共复习了 \(viewModel.totalCount) 个单词")
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

    private func emptyState(title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Text(title).font(.headline).foregroundColor(Theme.textPrimary)
            Text(subtitle).font(.caption).foregroundColor(Theme.textSecondary)
        }
    }

    private func cardContent(_ word: VocabularyWord) -> some View {
        VStack(spacing: 24) {
            Text("\(viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)

            Spacer()

            VStack(spacing: 16) {
                HStack {
                    Text(word.word).font(.system(size: 36, weight: .bold)).foregroundColor(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundColor(Theme.textSecondary)

                if viewModel.isFlipped {
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.title3)
                        .foregroundColor(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
                } else {
                    Text("点击翻转看释义")
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 220)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .onTapGesture { viewModel.flip() }
            .padding(.horizontal)

            Spacer()

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).font(.footnote).foregroundColor(Theme.unknown)
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
                .foregroundColor(color)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .disabled(viewModel.isSubmitting)
    }
}
