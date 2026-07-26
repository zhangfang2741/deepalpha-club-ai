// App/AppConfig.swift
import Foundation

/// 全局配置：后端地址等。
enum AppConfig {
    /// 生产环境（Railway，与 DeepAlphaChan 共用同一个后端服务）。
    static let baseURL = URL(string: "https://web-production-b1596.up.railway.app")!
    static let apiPrefix = "/api/v1/vocabulary"
    static let requestTimeout: TimeInterval = 30
    /// 拍照识别调 LLM，比普通请求慢很多，单独给更长超时。
    ///
    /// 90s 是经验值：必须 < Cloudflare 的边缘 idle timeout（实测 100s 左右），
    /// 否则 URLSession 会被 CFNetwork 在 socket idle 阶段直接 -1005 reset
    /// （kCFStreamErrorCodeKey=54）。90s 让 NSURLSession 主动触发超时重试，
    /// 而不是被底层掐断。
    static let recognizeTimeout: TimeInterval = 90
    /// 整体资源（上传 + 服务器处理 + 接收响应）总耗时上限。
    static let resourceTimeout: TimeInterval = 180
}
