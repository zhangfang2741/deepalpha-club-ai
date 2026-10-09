import SwiftUI
import UIKit

/// 图表横向平移，同时不挡外层页面的上下滚动。
///
/// iOS 18 起 SwiftUI 手势跑在 UIKit 手势系统上：ScrollView 里挂一个 DragGesture，
/// 即使是 simultaneousGesture、纵向时回调里直接 return，触摸也已被它占住，页面滚不动。
/// 所以 iOS 18+ 用 `HorizontalPanGesture`（UIKit 平移识别器，开始前按速度判方向，
/// 纵向直接不开始）；iOS 17 没有这个问题，仍用 SwiftUI 的 `fallback`。
struct ChartPanModifier<G: Gesture>: ViewModifier {
    let isEnabled: Bool
    let fallback: G
    /// (累计横向位移, 手指当前 x)
    let onChanged: (CGFloat, CGFloat) -> Void
    /// 预测落点比当前还会再滑多少像素（用于惯性）
    let onEnded: (CGFloat) -> Void

    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.gesture(HorizontalPanGesture(isEnabled: isEnabled, onChanged: onChanged, onEnded: onEnded))
        } else {
            content.simultaneousGesture(fallback, including: isEnabled ? .all : .none)
        }
    }
}

/// 只在横向拖动时开始的平移识别器。纵向拖动时 `gestureRecognizerShouldBegin` 返回 false，
/// 识别器立即失败，触摸由外层 ScrollView 接走。
@available(iOS 18.0, *)
struct HorizontalPanGesture: UIGestureRecognizerRepresentable {
    var isEnabled: Bool
    var onChanged: (CGFloat, CGFloat) -> Void
    var onEnded: (CGFloat) -> Void

    /// 惯性预测：沿用 UIScrollView 正常减速率（0.998 / 毫秒）的滑行距离 ≈ 速度 × 0.998 / (1 − 0.998) / 1000。
    private static let decelerationFactor: CGFloat = 0.998 / (1 - 0.998) / 1000

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        pan.maximumNumberOfTouches = 1   // 双指留给缩放
        return pan
    }

    func updateUIGestureRecognizer(_ recognizer: UIPanGestureRecognizer, context: Context) {
        recognizer.isEnabled = isEnabled
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        let tx = recognizer.translation(in: recognizer.view).x
        switch recognizer.state {
        case .began, .changed:
            onChanged(tx, context.converter.localLocation.x)
        case .ended:
            onEnded(recognizer.velocity(in: recognizer.view).x * Self.decelerationFactor)
        case .cancelled, .failed:
            onEnded(0)
        default:
            break
        }
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizerShouldBegin(_ g: UIGestureRecognizer) -> Bool {
            guard let pan = g as? UIPanGestureRecognizer else { return true }
            let v = pan.velocity(in: pan.view)
            return abs(v.x) > abs(v.y)
        }

        /// 与点按、双指缩放并存；但不与页面滚动同时进行（横向拖图时页面不跟着抖）。
        func gestureRecognizer(_ g: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
            !(other.view is UIScrollView)
        }
    }
}
