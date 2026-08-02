import SwiftUI

/// 右滑确认后的短暂保存状态。以系统结论为视觉主体，网络保存只作为次级进度，
/// 避免把一个临时加载提示孤零零地放在卡片中央。
struct DictationAcceptedState: View {
    let resultLabel: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.white)
                .accessibilityHidden(true)

            Text(resultLabel)
                .font(.headline.bold())
                .foregroundStyle(.white)

            HStack(spacing: 7) {
                ProgressView()
                    .controlSize(.small)
                    .tint(.white)
                Text("保存后进入下一个")
            }
            .font(.footnote)
            .foregroundStyle(.white)
        }
        .multilineTextAlignment(.center)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(resultLabel)，保存后进入下一个单词")
    }
}
