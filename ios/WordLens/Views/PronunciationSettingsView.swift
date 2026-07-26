import SwiftUI

/// 发音设置页面（从设置页进入）。
///
/// 把发音相关的所有偏好集中在一处：口音（英/美）、语速、自动发音。偏好本身仍存在
/// UserDefaults（见 PronounceButton.swift 里的 PronunciationAccent / PronunciationRate
/// / PronunciationAutoplay），这里只是统一的可视化入口。
struct PronunciationSettingsView: View {
    @State private var accent: PronunciationAccent = PronunciationAccent.current
    @State private var rate: PronunciationRate = PronunciationRate.current
    @State private var autoplay: Bool = PronunciationAutoplay.isEnabled

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
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
