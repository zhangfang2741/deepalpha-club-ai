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
                    ContentUnavailableView(
                        "未识别到英语单词",
                        systemImage: "text.viewfinder",
                        description: Text("请重新拍摄，确保文字清晰")
                    )
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
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))
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
                        .foregroundStyle(.white)
                        .clipShape(.rect(cornerRadius: 12))
                    }
                    .disabled(viewModel.selectedWords.isEmpty || isSubmitting)
                    .padding()
                    .background(Theme.background)
                }
            }
        }
    }

    private func candidateRow(_ candidate: RecognizedWord) -> some View {
        let isSelected = viewModel.selectedWords.contains(candidate.word)
        return HStack {
            Button("加入生词库", systemImage: isSelected ? "checkmark.square.fill" : "square") {
                viewModel.toggle(candidate.word)
            }
            .labelStyle(.iconOnly)
            .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(.rect)
            .buttonStyle(.plain)
            .accessibilityValue(isSelected ? "已选中" : "未选中")

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(candidate.word).fontWeight(.semibold)
                    PronounceButton(word: candidate.word)
                    Text("/\(candidate.phoneticIpa)/")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                Text("\(candidate.partOfSpeech) \(candidate.definitionZh)")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                if candidate.alreadyInLibrary {
                    Text("已在生词库中")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            Spacer()
        }
        .listRowBackground(Theme.surface)
        .foregroundStyle(Theme.textPrimary)
    }
}
