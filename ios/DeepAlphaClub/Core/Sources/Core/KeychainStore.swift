import Foundation
import Security

/// token 存取抽象：真 Keychain 与测试用内存实现。
public protocol KeychainStoring: Sendable {
    func saveToken(_ token: String) throws
    func loadToken() -> String?
    func deleteToken()
}

/// SecItem 实现（kSecClassGenericPassword，service=app bundle id，account=access_token）。
/// iOS / macOS 同 API；测试不要用真实现（污染开发机钥匙串），用 InMemoryKeychain。
public struct KeychainStore: KeychainStoring {
    let service: String
    let account: String

    public init(service: String = "club.deepalpha.ios", account: String = "access_token") {
        self.service = service
        self.account = account
    }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    public func saveToken(_ token: String) throws {
        deleteToken()
        var add = baseQuery
        add[kSecValueData as String] = Data(token.utf8)
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
    }

    public func loadToken() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func deleteToken() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

/// 测试 / SwiftUI 预览用内存实现。
public final class InMemoryKeychain: KeychainStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var token: String?
    public init() {}
    public func saveToken(_ token: String) throws {
        lock.lock(); defer { lock.unlock() }
        self.token = token
    }
    public func loadToken() -> String? {
        lock.lock(); defer { lock.unlock() }
        return token
    }
    public func deleteToken() {
        lock.lock(); defer { lock.unlock() }
        token = nil
    }
}
