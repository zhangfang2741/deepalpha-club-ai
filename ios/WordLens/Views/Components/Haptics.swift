// Views/Components/Haptics.swift
import UIKit

/// 评分按钮的触觉反馈：分三档通知类型，对应「认识/模糊/不认识」的语义强度。
///
/// success/warning/error 三档 iOS 系统通知反馈，比单档 impact 更有"判决感"——
// 认识 = 成功通关，模糊 = 有保留，不认识 = 需要重学。prepare() 提前预热避免
/// 首次按下延迟，generator 在每次调用时新建一个，因为 .prepare() 的状态在跨
/// 多次触发时不可靠（被 cancel/timeout 取消后第二次就哑火）。
enum Haptics {
    /// 评分反馈：认识 → success，模糊 → warning，不认识 → error。
    static func rating(_ rating: ReviewRating) {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        switch rating {
        case .known: generator.notificationOccurred(.success)
        case .fuzzy: generator.notificationOccurred(.warning)
        case .unknown: generator.notificationOccurred(.error)
        }
    }
}