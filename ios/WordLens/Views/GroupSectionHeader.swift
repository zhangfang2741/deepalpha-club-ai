// Views/GroupSectionHeader.swift
import SwiftUI

/// 分组下拉框的一级节点，使用更强的字号、图标和分隔来建立清晰层级。
struct GroupSectionHeader: View {
    let title: String
    let systemImage: String
    var separatesPreviousSection = false

    var body: some View {
        VStack(spacing: 0) {
            if separatesPreviousSection {
                Divider()
                    .padding(.horizontal, 16)
                    .padding(.bottom, 12)
            }

            Label(title, systemImage: systemImage)
                .font(.body.bold())
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.bottom, 6)
        }
        .padding(.top, separatesPreviousSection ? 8 : 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityAddTraits(.isHeader)
    }
}
