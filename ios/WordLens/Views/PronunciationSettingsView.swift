import SwiftUI

/// 发音设置页面（从设置页进入）。
///
/// 把发音相关的所有偏好集中在一处。单词与例句统一使用 MiniMax Speech HD，
/// 用户只需选择口音、语速和是否自动发音。
struct PronunciationSettingsView: View {
    @State private var accent: PronunciationAccent = PronunciationAccent.current
    @State private var rate: PronunciationRate = PronunciationRate.current
    @State private var autoplay: Bool = PronunciationAutoplay.isEnabled

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                // 单词和例句现在是同一个引擎，没必要再分两行列出来——
                // 那会让用户以为有两种可选方案，实际并没有得选。
                Section {
                    LabeledContent(L("发音引擎")) {
                        Text("MiniMax Speech HD")
                            .foregroundStyle(Theme.textSecondary)
                    }
                } header: {
                    Text(L("发音方案"))
                } footer: {
                    Text(L("单词与例句均使用高清语音合成，保留自然的连读、停顿和重音。"))
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)

                Section(L("口音")) {
                    Picker(L("口音"), selection: $accent) {
                        Text(L("美音")).tag(PronunciationAccent.us)
                        Text(L("英音")).tag(PronunciationAccent.uk)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: accent) { _, newValue in
                        PronunciationAccent.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section(L("语速")) {
                    Picker(L("语速"), selection: $rate) {
                        Text(L("慢速")).tag(PronunciationRate.slow)
                        Text(L("正常")).tag(PronunciationRate.normal)
                        Text(L("快速")).tag(PronunciationRate.fast)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: rate) { _, newValue in
                        PronunciationRate.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Toggle(L("自动发音"), isOn: $autoplay)
                        .tint(Theme.accent)
                        .onChange(of: autoplay) { _, newValue in
                            PronunciationAutoplay.isEnabled = newValue
                        }
                } footer: {
                    Text(L("开启后，复习和查看单词详情时会自动朗读。"))
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle(L("发音设置"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
