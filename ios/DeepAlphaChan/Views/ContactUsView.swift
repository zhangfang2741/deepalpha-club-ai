import SwiftUI

/// 联系我们：一个文本框，提交后由服务端发邮件给运营。
struct ContactUsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var isSending = false
    @State private var errorMessage: String?
    @State private var showDone = false

    private let maxLength = 2000

    private var trimmed: String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        Form {
            Section {
                TextEditor(text: $text)
                    .frame(minHeight: 180)
                    .onChange(of: text) { _, new in
                        if new.count > maxLength { text = String(new.prefix(maxLength)) }
                    }
            } footer: {
                Text(L("欢迎提出问题、建议或合作意向，我们会尽快查看。"))
            }

            if let errorMessage {
                Section { Text(errorMessage).foregroundColor(.red).font(.footnote) }
            }

            Section {
                Button {
                    Task { await send() }
                } label: {
                    HStack {
                        if isSending { ProgressView() }
                        Text(L("提交")).frame(maxWidth: .infinity)
                    }
                }
                .disabled(trimmed.isEmpty || isSending)
            }
        }
        .navigationTitle(L("联系我们"))
        .navigationBarTitleDisplayMode(.inline)
        .alert(L("已提交，谢谢你的反馈"), isPresented: $showDone) {
            Button(L("好"), role: .cancel) { dismiss() }
        }
    }

    private func send() async {
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        do {
            try await FeedbackService.submit(content: trimmed)
            text = ""
            showDone = true
        } catch {
            errorMessage = L("提交失败，请稍后再试")
        }
    }
}
