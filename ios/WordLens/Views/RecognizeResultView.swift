// Views/RecognizeResultView.swift
import SwiftUI

struct RecognizeResultView: View {
    @ObservedObject var viewModel: CameraViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false
    @State private var resultMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                if viewModel.candidates.isEmpty {
                    VStack(spacing: 12) {
                        Text("未识别到英语单词")
                            .foregroundColor(Theme.textSecondary)
                        Text("请重新拍摄，确保文字清晰")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                    }
                } else {
                    List(viewModel.candidates) { candidate in
                        candidateRow(candidate)
                    }
                    .scrollContentBackground(.hidden)
                }

                if let resultMessage {
                    VStack {
                        Spacer()
                        Text(resultMessage)
                            .padding()
                            .background(Theme.surfaceAlt)
                            .foregroundColor(Theme.textPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .padding(.bottom, 100)
                    }
                }
            }
            .navigationTitle("识别结果")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        viewModel.reset()
                        dismiss()
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                if !viewModel.candidates.isEmpty {
                    Button {
                        Task {
                            isSubmitting = true
                            let (added, skipped) = await viewModel.addSelectedToLibrary()
                            isSubmitting = false
                            if added > 0 || !skipped.isEmpty {
                                resultMessage = "加入 \(added) 个单词" + (skipped.isEmpty ? "" : "，\(skipped.count) 个已存在")
                                try? await Task.sleep(for: .seconds(1.2))
                                dismiss()
                            }
                        }
                    } label: {
                        HStack {
                            if isSubmitting { ProgressView().tint(.white) }
                            Text("加入生词库 (\(viewModel.selectedWords.count))")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(viewModel.selectedWords.isEmpty ? Theme.surfaceAlt : Theme.accent)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(viewModel.selectedWords.isEmpty || isSubmitting)
                    .padding()
                    .background(Theme.background)
                }
            }
        }
    }

    private func candidateRow(_ candidate: RecognizedWord) -> some View {
        HStack {
            Button {
                viewModel.toggle(candidate.word)
            } label: {
                Image(systemName: viewModel.selectedWords.contains(candidate.word) ? "checkmark.square.fill" : "square")
                    .foregroundColor(viewModel.selectedWords.contains(candidate.word) ? Theme.accent : Theme.textSecondary)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(candidate.word).fontWeight(.semibold)
                    PronounceButton(word: candidate.word)
                    Text("/\(candidate.phoneticIpa)/")
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                }
                Text("\(candidate.partOfSpeech) \(candidate.definitionZh)")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                if candidate.alreadyInLibrary {
                    Text("已在生词库中")
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
            }
            Spacer()
        }
        .listRowBackground(Theme.surface)
        .foregroundColor(Theme.textPrimary)
    }
}
