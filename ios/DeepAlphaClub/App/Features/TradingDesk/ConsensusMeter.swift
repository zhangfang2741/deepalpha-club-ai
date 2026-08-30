import SwiftUI
import DeepAlphaCore

/// 共识条：bull/neutral/bear 三段比例 + 计数说明。
struct ConsensusMeter: View {
    let consensus: ConsensusData?

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Text("共识").font(.caption2.monospaced()).foregroundStyle(Theme.textSecondary)
                Spacer()
                Text(consensus.map { "多\($0.bull) 中\($0.neutral) 空\($0.bear) · \($0.lean)" } ?? "—")
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            GeometryReader { geo in
                HStack(spacing: 0) {
                    if let c = consensus {
                        let total = max(c.bull + c.neutral + c.bear, 1)
                        Rectangle()
                            .fill(Theme.bull)
                            .frame(width: geo.size.width * CGFloat(c.bull) / CGFloat(total))
                        Rectangle()
                            .fill(Theme.neutral)
                            .frame(width: geo.size.width * CGFloat(c.neutral) / CGFloat(total))
                        Rectangle()
                            .fill(Theme.bear)
                            .frame(width: geo.size.width * CGFloat(c.bear) / CGFloat(total))
                    } else {
                        Rectangle().fill(Theme.surfaceAlt)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 2))
            }
            .frame(height: 8)
        }
    }
}
