import Foundation
import SwiftUI

@MainActor
class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published var isAuthenticated = false
    @Published var isLoading = false
    @Published var error: String?
    @Published var currentUserId: String?

    private init() {
        // Check for existing token
        if UserDefaults.standard.string(forKey: "accessToken") != nil {
            isAuthenticated = true
            currentUserId = UserDefaults.standard.string(forKey: "currentUserId")
        }

        // Listen for session expiry from APIClient
        APIClient.shared.onSessionExpired = { [weak self] in
            self?.handleSessionExpired()
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
        APIClient.shared.logout()
        isAuthenticated = false
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
