// Views/RegisterView.swift
import SwiftUI

struct RegisterView: View {
    /// 从登录页带过来，保持用户刚才选的方式，不用再切一次。
    let initialMethod: LoginView.LoginMethod

    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var method: LoginView.LoginMethod = .phone
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var code = ""
    /// 是否已经发过验证码。控制第二段（验证码栏 + 重发按钮）的出现。
    @State private var hasSentCode = false
    @State private var cooldown = 0
    @State private var cooldownTask: Task<Void, Never>?

    // 与后端 VOCABULARY_PASSWORD_MIN_LENGTH 保持一致：只校验长度，不做字符组合
    // 要求（NIST SP 800-63B 建议废弃组合规则，它不提升实际强度还抬高注册流失）。
    private var longEnough: Bool { password.count >= Self.passwordMinLength }
    private var matched: Bool { !password.isEmpty && password == confirmPassword }

    private static let passwordMinLength = 6

    /// 第一段只要求邮箱和密码填好；第二段还要求验证码填满 6 位。
    private var canSubmit: Bool {
        guard !email.isEmpty, longEnough, matched else { return false }
        return hasSentCode ? code.count == 6 : true
    }

    private var codeHintText: String {
        // 短信签名是服务商提供的【恒创联众】而不是 App 名——不提前说明的话，
        // 用户很容易把这条来自陌生公司的短信当成垃圾短信忽略掉。
        method == .phone
            ? "验证码已发往 \(email)，10 分钟内有效。短信签名为【恒创联众】，请注意查收。"
            : "验证码已发往 \(email)，10 分钟内有效。没收到请检查垃圾邮件。"
    }

    private var primaryButtonTitle: String {
        if auth.isLoading { return hasSentCode ? "注册中…" : "发送中…" }
        return hasSentCode ? "完成注册" : "发送验证码"
    }

    private func startCooldown() {
        cooldownTask?.cancel()
        cooldown = 60
        cooldownTask = Task { @MainActor in
            while cooldown > 0 {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                cooldown -= 1
            }
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 16) {
                        SegmentedToggle(
                            options: LoginView.LoginMethod.allCases,
                            label: \.label,
                            selection: $method
                        )
                        // 发过码后再切会让已发的码作废，直接禁用并压暗
                        .disabled(hasSentCode)
                        .opacity(hasSentCode ? 0.5 : 1)
                        .onChange(of: method) { _, _ in
                            email = ""
                            code = ""
                            auth.clearError()
                        }

                        TextField(method.placeholder, text: $email)
                            .keyboardType(method == .phone ? .phonePad : .emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        SecureField("密码", text: $password)
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        SecureField("确认密码", text: $confirmPassword)
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        VStack(alignment: .leading, spacing: 6) {
                            checklistRow("至少 \(Self.passwordMinLength) 个字符", longEnough)
                            checklistRow("两次密码一致", matched)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        // 验证码栏只在发过码之后出现：一上来就摆一个空的验证码框，
                        // 用户会以为要先去别处找码。
                        if hasSentCode {
                            TextField(method == .phone ? "短信收到的 6 位验证码" : "邮箱收到的 6 位验证码", text: $code)
                                .keyboardType(.numberPad)
                                .textContentType(.oneTimeCode)
                                .onChange(of: code) { _, new in
                                    code = String(new.filter(\.isNumber).prefix(6))
                                }
                                .padding()
                                .background(Theme.surface)
                                .foregroundStyle(Theme.textPrimary)
                                .clipShape(.rect(cornerRadius: 10))

                            Text(codeHintText)
                                .font(.caption)
                                .foregroundStyle(Theme.textSecondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        if let errorMessage = auth.errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundStyle(Theme.unknown)
                        }

                        Button {
                            Task {
                                if hasSentCode {
                                    switch method {
                                    case .phone:
                                        await auth.registerByPhone(phone: email, password: password, code: code)
                                    case .email:
                                        await auth.register(email: email, password: password, code: code)
                                    }
                                    if auth.isAuthenticated { dismiss() }
                                } else {
                                    let sent = method == .phone
                                        ? await auth.requestPhoneRegisterCode(phone: email)
                                        : await auth.requestRegisterCode(email: email)
                                    if sent {
                                        hasSentCode = true
                                        startCooldown()
                                    }
                                }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(primaryButtonTitle).fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundStyle(.white)
                            .clipShape(.rect(cornerRadius: 12))
                        }
                        .buttonStyle(.pressable)
                        .disabled(!canSubmit || auth.isLoading)

                        if hasSentCode {
                            Button(cooldown > 0 ? "重新发送（\(cooldown)s）" : "重新发送验证码") {
                                Task {
                                    let sent = method == .phone
                                        ? await auth.requestPhoneRegisterCode(phone: email)
                                        : await auth.requestRegisterCode(email: email)
                                    if sent { startCooldown() }
                                }
                            }
                            .font(.footnote)
                            .foregroundStyle(cooldown > 0 ? Theme.textSecondary : Theme.accent)
                            .disabled(cooldown > 0 || auth.isLoading)
                        }

                        // 用户在这一步才第一次交出邮箱和密码，法务文本必须在
                        // 提交之前就够得着。设置页那两个入口要登录后才能进，
                        // 覆盖不到注册这个真正的收集时点。
                        legalConsentNotice
                    }
                    .padding(24)
                }
            }
            .navigationTitle("注册")
            .onAppear { method = initialMethod }
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    /// 注册按钮下方的条款告知。用 Text 拼接而不是三段 HStack：中文换行位置
    /// 由系统决定，硬拼会在窄屏和大字号下断得很难看。
    private var legalConsentNotice: some View {
        VStack(spacing: 6) {
            Text("点击「注册」即表示你已阅读并同意")
            HStack(spacing: 4) {
                Link("《服务条款》", destination: AppConfig.termsOfServiceURL)
                Text("和")
                Link("《隐私政策》", destination: AppConfig.privacyPolicyURL)
            }
        }
        .font(.caption)
        .foregroundStyle(Theme.textSecondary)
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
        .accessibilityElement(children: .combine)
    }

    private func checklistRow(_ text: String, _ satisfied: Bool) -> some View {
        HStack(spacing: 6) {
            // 图标是文字状态的视觉复述，对 VoiceOver 隐藏，避免"勾选，至少8个字符"这种
            // 冗余读法；改成把满足状态并进这一行的组合 label 里一次性读出。
            Image(systemName: satisfied ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(satisfied ? Theme.known : Theme.textSecondary)
                .accessibilityHidden(true)
            Text(text)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(text)，\(satisfied ? "已满足" : "未满足")")
    }
}
