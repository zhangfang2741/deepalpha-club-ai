import Foundation

/// 全局配置：后端地址等。
///
/// 默认直连生产环境（Railway）。
/// 本地联调时把 `baseURL` 改为 `http://localhost:8000`，
/// 并在 Info.plist 里为 localhost 放开 ATS（工程已配置）。
enum AppConfig {
    /// 后端 API 根地址（不含 `/api/v1` 前缀）。
    static let baseURL = URL(string: "https://web-production-b1596.up.railway.app")!

    /// 所有业务接口的公共前缀。
    static let apiPrefix = "/api/v1/vocabulary"

    /// 网络请求超时（秒）。
    static let requestTimeout: TimeInterval = 30

    /// 拍照识别超时（秒）。图像上传和后端推理可能较慢，放宽一些。
    static let recognizeTimeout: TimeInterval = 60
}
