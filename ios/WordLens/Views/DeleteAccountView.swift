// Views/DeleteAccountView.swift
import SwiftUI

/// 删除账号确认页。
///
/// App Store 审核指南 5.1.1(v) 要求有注册功能的 App 必须提供 App 内自助删除账号
/// 的入口，且路径不能藏得太深。这里做成三道关：先看清删什么 → 输密码 → 再确认
/// 一次。删号不可恢复，多一道确认远比事后道歉便宜。
struct DeleteAccountView: View {
    @ObservedObject var viewModel: SettingsViewModel
    /// 删除成功后的回调，由调用方负责登出并跳回登录页。
    let onDeleted: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var isConfirmDialogPresented = false

    private var canSubmit: Bool { !password.isEmpty && !viewModel.isDeletingAccount }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                Form {
                    Section {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("此操作不可恢复", systemImage: "exclamationmark.triangle.fill")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(Theme.unknown)

                            Text("删除后，以下数据会被永久清除，无法找回：")
                                .font(.footnote)
                                .foregroundStyle(Theme.textSecondary)

                            VStack(alignment: .leading, spacing: 6) {
                                deletedItemRow("你的账号与登录信息")
                                deletedItemRow("全部生词及其释义、例句")
                                deletedItemRow("所有复习进度与历史记录")
                                deletedItemRow("所有自建歌单")
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowBackground(Theme.surface)

                    Section {
                        SecureField("当前密码", text: $password)
                            .textContentType(.password)
                    } header: {
                        Text("输入密码确认身份")
                    } footer: {
                        Text("为防止误删，需要重新输入一次密码。")
                            .font(.caption)
                            .foregroundStyle(Theme.textSecondary)
                    }
                    .listRowBackground(Theme.surface)

                    if let errorMessage = viewModel.deleteErrorMessage {
                        Section {
                            Label(errorMessage, systemImage: "exclamationmark.circle.fill")
                                .font(.footnote)
                                .foregroundStyle(Theme.unknown)
                        }
                        .listRowBackground(Theme.surface)
                    }

                    Section {
                        Button(role: .destructive) {
                            isConfirmDialogPresented = true
                        } label: {
                            HStack(spacing: 10) {
                                if viewModel.isDeletingAccount {
                                    ProgressView().tint(Theme.unknown)
                                }
                                Text(viewModel.isDeletingAccount ? "正在删除..." : "永久删除账号")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .disabled(!canSubmit)
                    }
                    .listRowBackground(Theme.surface)
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("删除账号")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                        .disabled(viewModel.isDeletingAccount)
                }
            }
            .interactiveDismissDisabled(viewModel.isDeletingAccount)
            .confirmationDialog(
                "确定要永久删除账号吗？",
                isPresented: $isConfirmDialogPresented,
                titleVisibility: .visible
            ) {
                Button("永久删除", role: .destructive) {
                    Task { await submit() }
                }
                Button("再想想", role: .cancel) {}
            } message: {
                Text("你的生词库和复习进度都会被清空，且无法恢复。")
            }
        }
    }

    private func submit() async {
        guard await viewModel.deleteAccount(password: password) else { return }
        password = ""
        dismiss()
        onDeleted()
    }

    private func deletedItemRow(_ title: String) -> some View {
        Label {
            Text(title)
                .font(.footnote)
                .foregroundStyle(Theme.textPrimary)
        } icon: {
            Image(systemName: "xmark.circle.fill")
                .font(.caption)
                .foregroundStyle(Theme.unknown)
        }
        .accessibilityElement(children: .combine)
    }
}
