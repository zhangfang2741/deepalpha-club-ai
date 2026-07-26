import SwiftUI

/// 发音设置页面（从设置页进入）。
///
/// 把发音相关的所有偏好集中在一处：发音源（有道/Google/系统/Azure）、口音（英/美）、
/// 语速、自动发音。偏好本身仍存在 UserDefaults（见 PronounceButton.swift 里的
/// PronunciationSource / PronunciationAccent / PronunciationRate / PronunciationAutoplay），
/// 这里只是统一的可视化入口。
struct PronunciationSettingsView: View {
    @State private var source: PronunciationSource = PronunciationSource.current
    @State private var accent: PronunciationAccent = PronunciationAccent.current
    @State private var rate: PronunciationRate = PronunciationRate.current
    @State private var autoplay: Bool = PronunciationAutoplay.isEnabled

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section {
                    Picker("发音源", selection: $source) {
                        Text("有道").tag(PronunciationSource.youdao)
                        Text("Google").tag(PronunciationSource.google)
                        Text("系统语音").tag(PronunciationSource.system)
                        Text("高清（Azure）").tag(PronunciationSource.azure)
                    }
                    .onChange(of: source) { _, newValue in
                        PronunciationSource.current = newValue
                    }
                } header: {
                    Text("发音源")
                } footer: {
                    Text("有道：常见词真人录音；Google：神经网络合成，咬字清晰、覆盖全；系统语音：Apple 离线合成，需先在「设置 › 辅助功能 › 朗读内容 › 声音」里下载优质英语语音；高清：Azure 神经语音，质量最稳定、词句通吃（联网）。")
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)

                Section("口音") {
                    Picker("口音", selection: $accent) {
                        Text("美音").tag(PronunciationAccent.us)
                        Text("英音").tag(PronunciationAccent.uk)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: accent) { _, newValue in
                        PronunciationAccent.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section("语速") {
                    Picker("语速", selection: $rate) {
                        Text("慢速").tag(PronunciationRate.slow)
                        Text("正常").tag(PronunciationRate.normal)
                        Text("快速").tag(PronunciationRate.fast)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: rate) { _, newValue in
                        PronunciationRate.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Toggle("自动发音", isOn: $autoplay)
                        .tint(Theme.accent)
                        .onChange(of: autoplay) { _, newValue in
                            PronunciationAutoplay.isEnabled = newValue
                        }
                } footer: {
                    Text("开启后，复习和查看单词详情时会自动朗读。")
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("发音设置")
        .navigationBarTitleDisplayMode(.inline)
    }
}
