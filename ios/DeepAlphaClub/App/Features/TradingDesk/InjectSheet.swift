import SwiftUI

/// 注入人工意见：多行输入 + 提交。
struct InjectSheet: View {
    let onSubmit: (String) -> Void
    @State private var text = ""
    @Environment(\.dismiss) private var dismiss

    private var trimmed: String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("给交易台补一条上下文 —— 例如「把出口管制风险的权重调高」",
                              text: $text, axis: .vertical)
                        .lineLimit(3...6)
                } footer: {
                    Text("意见会在下一个节点边界注入引擎状态，作为人工上下文参与后续推理。")
                }
            }
            .scrollContentBackground(.hidden)
            .themedBackground()
            .navigationTitle("注入意见")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("加入") {
                        // 后端对空 text 返回 422，这里先行拦住
                        guard !trimmed.isEmpty else { return }
                        onSubmit(trimmed)
                        dismiss()
                    }
                    .disabled(trimmed.isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
