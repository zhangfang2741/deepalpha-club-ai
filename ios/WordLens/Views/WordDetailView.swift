// Views/WordDetailView.swift
import SwiftUI

struct WordDetailView: View {
    let word: VocabularyWord
    @ObservedObject var listViewModel: WordListViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showDeleteConfirm = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 20) {
                VStack(spacing: 8) {
                    HStack {
                        Text(word.word).font(.largeTitle.bold()).foregroundColor(Theme.textPrimary)
                        PronounceButton(word: word.word)
                    }
                    Text("/\(word.phoneticIpa)/").foregroundColor(Theme.textSecondary)
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .foregroundColor(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                }
                .padding()

                VStack(alignment: .leading, spacing: 8) {
                    detailRow("状态", statusLabel)
                    detailRow("连续认识次数", "\(word.repetitionCount)")
                    detailRow("复习间隔", "\(word.intervalDays) 天")
                    detailRow("下次复习", word.nextReviewAt)
                }
                .padding()
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Spacer()

                Button(role: .destructive) {
                    showDeleteConfirm = true
                } label: {
                    Text("删除单词")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.surface)
                        .foregroundColor(Theme.unknown)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding()
        }
        .navigationTitle("单词详情")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("确定删除「\(word.word)」吗？", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("删除", role: .destructive) {
                Task {
                    await listViewModel.delete(word)
                    dismiss()
                }
            }
            Button("取消", role: .cancel) {}
        }
    }

    private var statusLabel: String {
        switch word.status {
        case "known": return "认识"
        case "fuzzy": return "模糊"
        default: return "不认识"
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundColor(Theme.textSecondary)
            Spacer()
            Text(value).foregroundColor(Theme.textPrimary)
        }
        .font(.subheadline)
    }
}
