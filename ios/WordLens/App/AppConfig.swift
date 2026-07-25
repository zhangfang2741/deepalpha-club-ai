// App/AppConfig.swift
import Foundation

/// 全局配置：后端地址等。
enum AppConfig {
    /// 手机和 Mac 同一 WiFi 下，指向 Mac 的局域网 IP（`make dev` 起的后端，监听 0.0.0.0:8000）。
    /// 这个 IP 是路由器 DHCP 分配的，可能会变——连不上时先在 Mac 终端跑
    /// `ipconfig getifaddr en0` 确认当前 IP，变了就改这里。
    static let baseURL = URL(string: "http://192.168.1.7:8000")!
    static let apiPrefix = "/api/v1/vocabulary"
    static let requestTimeout: TimeInterval = 30
    /// 拍照识别调 LLM，比普通请求慢很多，单独给更长超时。
    static let recognizeTimeout: TimeInterval = 60
}
