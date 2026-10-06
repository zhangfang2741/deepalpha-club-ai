import Foundation

/// 联系我们：提交一段文字，服务端转成邮件发给运营。
enum FeedbackService {
    static func submit(email: String, content: String) async throws {
        struct Body: Encodable { let email: String; let content: String }
        struct Resp: Decodable { let sent: Bool }
        let _: Resp = try await APIClient.shared.postJSON("/feedback", body: Body(email: email, content: content))
    }
}
