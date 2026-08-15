// Views/ForgotPasswordView.swift
import SwiftUI

/// 找回密码：填邮箱 → 收验证码 → 设新密码。
///
/// 做成单页两段而不是两个页面：验证码只有 10 分钟有效，用户在页面之间来回跳
/// 容易忘了自己填的是哪个邮箱；留在同一页上，邮箱始终可见，也方便发现填错了。
struct ForgotPasswordView: View {
    /// 从登录页带过来，省得用户再输一遍。
    let initialEmail: String

    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = ForgotPasswordViewModel()

    @State private var email = ""
    @State private var code = ""
    @State private var newPassword = ""

    private static let passwordMinLength = 6

    private var canSend: Bool { email.contains("@") && !viewModel.isSending }
    private var canSubmit: Bool {
        code.count == 6 && newPassword.count >= Self.passwordMinLength && !viewModel.isSubmitting
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                Form {
                    Section {
                        TextField("注册时使用的邮箱", text: $email)
                            .textContentType(.username)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .disabled(viewModel.hasSentCode)

                        Button {
                            Task { await viewModel.sendCode(email: email) }
                        } label: {
                            HStack(spacing: 10) {
                                if viewModel.isSending { ProgressView().tint(Theme.accent) }
                                Text(sendButtonTitle)
                            }
                            .foregroundStyle(canSend && viewModel.cooldown == 0 ? Theme.accent : Theme.textSecondary)
                        }
                        .disabled(!canSend || viewModel.cooldown > 0)
                    } header: {
                        Text("第一步：获取验证码")
                    } footer: {
                        if viewModel.hasSentCode {
                            // 后端对未注册邮箱也返回成功（防账号枚举），文案必须跟着含糊，
                            // 不能写成「验证码已发送」那样暗示邮箱一定存在。
                            Text("如果该邮箱已注册，验证码已发出，10 分钟内有效。没收到请检查垃圾邮件。")
                        }
                    }
                    .listRowBackground(Theme.surface)

                    if viewModel.hasSentCode {
                        Section {
                            TextField("6 位验证码", text: $code)
                                .keyboardType(.numberPad)
                                .textContentType(.oneTimeCode)
                                .onChange(of: code) { _, new in
                                    code = String(new.filter(\.isNumber).prefix(6))
                                }

                            SecureField("新密码", text: $newPassword)
                                .textContentType(.newPassword)
                        } header: {
                            Text("第二步：设置新密码")
                        } footer: {
                            Text("新密码至少 \(Self.passwordMinLength) 个字符")
                        }
                        .listRowBackground(Theme.surface)
                    }

                    if let message = viewModel.errorMessage {
                        Section {
                            Label(message, systemImage: "exclamationmark.circle.fill")
                                .font(.footnote)
                                .foregroundStyle(Theme.unknown)
                        }
                        .listRowBackground(Theme.surface)
                    }

                    if viewModel.hasSentCode {
                        Section {
                            Button {
                                Task {
                                    let ok = await viewModel.resetPassword(
                                        email: email, code: code, newPassword: newPassword
                                    )
                                    if ok { dismiss() }
                                }
                            } label: {
                                HStack(spacing: 10) {
                                    if viewModel.isSubmitting { ProgressView().tint(Theme.accent) }
                                    Text(viewModel.isSubmitting ? "提交中..." : "重置密码")
                                        .frame(maxWidth: .infinity)
                                }
                                .foregroundStyle(Theme.accent)
                            }
                            .disabled(!canSubmit)
                        }
                        .listRowBackground(Theme.surface)
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("找回密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
            .onAppear { if email.isEmpty { email = initialEmail } }
        }
    }

    private var sendButtonTitle: String {
        if viewModel.cooldown > 0 { return "重新发送（\(viewModel.cooldown)s）" }
        return viewModel.hasSentCode ? "重新发送验证码" : "发送验证码"
    }
}

@MainActor
final class ForgotPasswordViewModel: ObservableObject {
    @Published private(set) var isSending = false
    @Published private(set) var isSubmitting = false
    @Published private(set) var hasSentCode = false
    @Published private(set) var errorMessage: String?
    /// 重发倒计时，与后端的冷却期对齐，避免用户狂点然后收到 429。
    @Published private(set) var cooldown = 0

    private var cooldownTask: Task<Void, Never>?

    func sendCode(email: String) async {
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        do {
            try await AuthService.requestPasswordReset(email: email)
            hasSentCode = true
            startCooldown()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "发送失败，请检查网络后重试"
        }
    }

    func resetPassword(email: String, code: String, newPassword: String) async -> Bool {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            try await AuthService.confirmPasswordReset(
                email: email, code: code, newPassword: newPassword
            )
            return true
        } catch let error as APIError {
            errorMessage = error.message
            return false
        } catch {
            errorMessage = "重置失败，请稍后再试"
            return false
        }
    }

    private func startCooldown() {
        cooldownTask?.cancel()
        cooldown = 60
        // 本类是 @MainActor，Task 继承同一个 actor 上下文，
        // 所以循环体里读写 cooldown 不需要再 await 或跳 MainActor.run。
        cooldownTask = Task { [weak self] in
            while true {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled, let self else { return }
                self.cooldown -= 1
                if self.cooldown <= 0 { return }
            }
        }
    }

    deinit { cooldownTask?.cancel() }
}
