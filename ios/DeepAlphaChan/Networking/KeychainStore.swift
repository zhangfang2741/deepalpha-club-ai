import Foundation
import Security

/// 极简 Keychain 封装，用来安全保存 JWT。
/// 比 UserDefaults 安全：不进 iTunes/iCloud 明文备份，App 卸载即清除。
enum KeychainStore {
    private static let service = "club.deepalpha.chan"
    private static let tokenAccount = "access_token"

    static func saveToken(_ token: String) {
        save(key: tokenAccount, value: token)
    }

    static func loadToken() -> String? {
        load(key: tokenAccount)
    }

    static func clearToken() {
        delete(key: tokenAccount)
    }

    // MARK: - 底层读写

    private static func save(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)  // 先删旧值，保证唯一
        var attrs = query
        attrs[kSecValueData as String] = data
        attrs[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(attrs as CFDictionary, nil)
    }

    private static func load(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let value = String(data: data, encoding: .utf8) else {
            return nil
        }
        return value
    }

    private static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
