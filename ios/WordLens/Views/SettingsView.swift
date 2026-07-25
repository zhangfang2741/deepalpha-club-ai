// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var accent: PronunciationAccent = PronunciationAccent.current

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section("发音口音") {
                    Picker("口音", selection: $accent) {
                        Text("美式").tag(PronunciationAccent.american)
                        Text("英式").tag(PronunciationAccent.british)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: accent) { _, newValue in
                        PronunciationAccent.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button("退出登录", role: .destructive) {
                        auth.logout()
                    }
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("设置")
        .navigationBarTitleDisplayMode(.inline)
    }
}
