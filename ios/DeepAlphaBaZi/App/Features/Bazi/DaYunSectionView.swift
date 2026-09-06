import SwiftUI

/// 大运流年展开：付费墙锁定态 UI。真实 StoreKit 购买接入是下一个 Plan 的工作，
/// 这里先把"未订阅时长什么样"做出来。
struct DaYunSectionView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("订阅解锁大运流年详细展开")
            Text("即将推出")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
    }
}
