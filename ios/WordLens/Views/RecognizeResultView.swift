// Views/RecognizeResultView.swift
import SwiftUI

struct RecognizeResultView: View {
    @ObservedObject var viewModel: CameraViewModel
    @EnvironmentObject var nav: AppNavigationState
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false
    @State private var resultMessage: String?
    /// 取消 = 丢弃整批识别结果，而且识别本身要等几十秒、烧 LLM 调用，误触的代价
    /// 很高（只能重拍重跑），所以加一道确认。
    @State private var showCancelConfirmation = false

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

                // 顶部错误条：addSelectedToLibrary 失败时把错误写进 viewModel.errorMessage
                // —— 必须在 sheet 上把这个状态显示给用户, 否则表现就是「按钮转一下
                // 就停了但什么都没发生」, 让人以为是 bug. 成功提交后 (reset() 会把
                // errorMessage 清空) 这个 VStack 自动消失.
                if let error = viewModel.errorMessage {
                    VStack {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(Theme.unknown)
                            Text(error)
                                .font(.footnote)
                                .foregroundStyle(Theme.textPrimary)
                                .lineLimit(2)
                            Spacer()
                            Button("重试") {
                                viewModel.errorMessage = nil
                                Task { await submitAsync() }
                            }
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(Theme.accent)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(Theme.surface)
                        .clipShape(.rect(cornerRadius: 10))
                        .padding(.horizontal)
                        .padding(.top, 8)
                        Spacer()
                    }
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
                        showCancelConfirmation = true
                    }
                }
            }
            .confirmationDialog(
                "放弃这次识别结果？",
                isPresented: $showCancelConfirmation,
                titleVisibility: .visible
            ) {
                Button("放弃", role: .destructive) {
                    viewModel.reset()
                    dismiss()
                }
                Button("继续挑选", role: .cancel) {}
            } message: {
                Text("识别出的 \(viewModel.candidates.count) 个单词都不会保存，需要重新拍照才能再次识别。")
            }
            .safeAreaInset(edge: .bottom) {
                if !viewModel.candidates.isEmpty {
                    // 三个数字的口径不一样，原来看板上"已识别 N 个"和按钮上的
                    // "加入生词库 (M)"摆在一起很容易被当成"对不上"：
                    //   - 已识别 N 个 = 全部候选词（识别阶段从后端推过来的总数）
                    //   - M 个已在库内 = N 里面已经收过的，默认不勾选，也不是新词
                    //   - K 个待加入 = 用户实际勾选、且不在库内的，会被加进去
                    // 按钮上 K 一直在变（M 固定），用同一行三段式说明把这层关系
                    // 讲清楚，"对不上"的感觉就消失了。
                    VStack(spacing: 6) {
                        summaryLine
                        Button {
                            Task { await submitAsync() }
                        } label: {
                            HStack {
                                if isSubmitting { ProgressView().tint(.white) }
                                Text("加入生词库 (\(viewModel.selectedWords.count))")
                                    .fontWeight(.semibold)
                                    .monospacedDigit()
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(viewModel.selectedWords.isEmpty ? Theme.surfaceAlt : Theme.accent)
                            .foregroundStyle(.white)
                            .clipShape(.rect(cornerRadius: 12))
                        }
                        .buttonStyle(.pressable)
                        .disabled(viewModel.selectedWords.isEmpty || isSubmitting)
                    }
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
            .buttonStyle(.pressable)
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

    /// 按钮上方那行小字：把"全部候选 / 已在库内 / 实际待加入"三件事讲清楚，
    /// 避免"已识别 N 个"和"加入生词库 (M)"看起来对不上。
    private var summaryLine: some View {
        let total = viewModel.candidates.count
        let inLibrary = viewModel.candidates.filter(\.alreadyInLibrary).count
        let selected = viewModel.selectedWords.count
        let parts: [(String, Int)] = [
            ("已识别", total),
            ("在库内", inLibrary),
            ("勾选", selected),
        ]
        return HStack(spacing: 12) {
            ForEach(parts.indices, id: \.self) { idx in
                let (label, value) = parts[idx]
                HStack(spacing: 4) {
                    Text(label).foregroundStyle(Theme.textSecondary)
                    Text("\(value)")
                        .monospacedDigit()
                        .foregroundStyle(idx == 2 ? Theme.accent : Theme.textPrimary)
                        .fontWeight(idx == 2 ? .semibold : .regular)
                }
                if idx < parts.count - 1 {
                    Text("·").foregroundStyle(Theme.textSecondary)
                }
            }
            Spacer()
        }
        .font(.caption)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("已识别 \(total) 个，其中 \(inLibrary) 个已在生词库内，已勾选 \(selected) 个准备加入")
    }

    /// 把「点底部加入按钮」和「点错误条上的重试」收敛到同一个提交逻辑里。
    /// 区别只在进入时是否需要先清错误状态——重试按钮自己已经清过了。
    ///
    /// 失败处理的关键：addSelectedToLibrary 把错误写到 viewModel.errorMessage
    /// 但不抛, 也不会让 (added, skipped) 非空. 老代码就靠这点返回空来判断"成功
    /// 还是失败"——错误成功都走完一遍, 用户点击只看到 spinner 闪一下, 完全
    /// 不知道发生了什么. 把这条修成: 失败时 (added.isEmpty && skipped.isEmpty)
    /// 也不再 dismiss, 让 sheet 留着, 让错误条自动浮起来.
    private func submitAsync() async {
        isSubmitting = true
        defer { isSubmitting = false }
        let (added, skipped) = await viewModel.addSelectedToLibrary()
        guard viewModel.errorMessage == nil else {
            // 提交失败——错误条已经显示, sheet 不关, 让用户选择重试 / 取消
            return
        }
        resultMessage = "加入 \(added.count) 个单词" + (skipped.isEmpty ? "" : "，\(skipped.count) 个已存在")
        try? await Task.sleep(for: .seconds(1.2))
        if !added.isEmpty {
            // 跳到生词库 tab 并高亮刚加入的词，而不是留在拍照页——
            // 加完词之后更想看到"加进去了什么"，不是继续对着相机页发呆。
            nav.showNewlyAddedWords(added.map(\.id))
        }
        dismiss()
    }
}
