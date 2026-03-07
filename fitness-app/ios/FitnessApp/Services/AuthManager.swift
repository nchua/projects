import Foundation
import SwiftUI

@MainActor
class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published var isAuthenticated = false
    @Published var isValidatingSession = false
    @Published var isLoading = false
    @Published var error: String?
    @Published var currentUserId: String?

    private init() {
        // One-time migration: move tokens from UserDefaults to Keychain
        migrateTokensToKeychain()

        // Check for existing token
        if KeychainManager.shared.get(forKey: "accessToken") != nil {
            isAuthenticated = true
            isValidatingSession = true
            currentUserId = UserDefaults.standard.string(forKey: "currentUserId")

            Task {
                await validateSession()
            }
        }

        // Listen for session expiry from APIClient
        APIClient.shared.onSessionExpired = { [weak self] in
            self?.handleSessionExpired()
        }
    }

    private func migrateTokensToKeychain() {
        let defaults = UserDefaults.standard
        let migrationKey = "didMigrateTokensToKeychain"

        guard !defaults.bool(forKey: migrationKey) else { return }

        if let accessToken = defaults.string(forKey: "accessToken") {
            KeychainManager.shared.set(accessToken, forKey: "accessToken")
            defaults.removeObject(forKey: "accessToken")
        }
        if let refreshToken = defaults.string(forKey: "refreshToken") {
            KeychainManager.shared.set(refreshToken, forKey: "refreshToken")
            defaults.removeObject(forKey: "refreshToken")
        }

        defaults.set(true, forKey: migrationKey)
    }

    private func validateSession() async {
        do {
            _ = try await APIClient.shared.getProfile()
            isValidatingSession = false
        } catch APIError.unauthorized {
            logout()
        } catch {
            // Network error — keep authenticated, user is likely offline
            isValidatingSession = false
        }
    }

    private func handleSessionExpired() {
        // Clear tokens and redirect to login
        logout()
        error = "Session expired. Please sign in again."
    }

    func register(email: String, password: String) async {
        isLoading = true
        error = nil

        do {
            _ = try await APIClient.shared.register(email: email, password: password)
            // Auto-login after registration
            await login(email: email, password: password)
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }

    func login(email: String, password: String) async {
        isLoading = true
        error = nil

        do {
            let response = try await APIClient.shared.login(email: email, password: password)
            currentUserId = response.accessToken // Store user ID if available
            UserDefaults.standard.set(currentUserId, forKey: "currentUserId")
            isAuthenticated = true
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func logout() {
        // Deactivate device token and cancel notifications
        Task {
            await NotificationManager.shared.deactivateDeviceToken()
        }
        NotificationManager.shared.cancelAllPendingNotifications()

        APIClient.shared.logout()
        isAuthenticated = false
        isValidatingSession = false
        currentUserId = nil
        UserDefaults.standard.removeObject(forKey: "currentUserId")
    }

    func refreshToken() async {
        do {
            _ = try await APIClient.shared.refreshAccessToken()
        } catch {
            // If refresh fails, log out
            logout()
        }
    }
}
