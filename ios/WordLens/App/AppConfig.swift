// App/AppConfig.swift
import Foundation

/// 全局配置：后端地址等。
enum AppConfig {
    /// 生产环境（Railway，与 DeepAlphaChan 共用同一个后端服务）。
    static let baseURL = URL(string: "https://web-production-b1596.up.railway.app")!
    static let apiPrefix = "/api/v1/vocabulary"
    static let requestTimeout: TimeInterval = 30
    /// 拍照识别调 LLM，比普通请求慢很多，单独给更长超时。
    static let recognizeTimeout: TimeInterval = 60
}
