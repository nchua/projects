import Foundation
import Security

/// Lightweight Keychain wrapper using Security.framework directly.
enum KeychainHelper {

    enum KeychainError: Error {
        case saveFailed(OSStatus)
        case readFailed
        case deleteFailed(OSStatus)
    }

    /// Save data to Keychain.
    @discardableResult
    static func save(key: String, data: Data) throws -> Bool {
        // Delete existing item first to avoid errSecDuplicateItem
        let deleteQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(deleteQuery as CFDictionary)

        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]

        let status = SecItemAdd(addQuery as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainError.saveFailed(status)
        }
        return true
    }

    /// Save a string to Keychain.
    @discardableResult
    static func save(key: String, string: String) throws -> Bool {
        guard let data = string.data(using: .utf8) else { return false }
        return try save(key: key, data: data)
    }

    /// Read data from Keychain.
    static func read(key: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess else { return nil }
        return result as? Data
    }

    /// Read a string from Keychain.
    static func readString(key: String) -> String? {
        guard let data = read(key: key) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Delete an item from Keychain.
    @discardableResult
    static func delete(key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
        ]
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    /// Check if a key exists in Keychain.
    static func exists(key: String) -> Bool {
        read(key: key) != nil
    }
}
