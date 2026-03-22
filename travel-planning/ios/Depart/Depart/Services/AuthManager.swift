import Foundation

/// Manages authentication lifecycle with invisible auto-registration.
/// On first launch, generates a UUID-based email and random password,
/// registers with the backend, and stores JWT tokens in Keychain.
@Observable
final class AuthManager {
    private(set) var isAuthenticated = false
    private(set) var currentUserId: UUID?
    private(set) var userProfile: UserProfile?

    private var apiClient: APIClient?

    // Keychain keys
    private enum Keys {
        static let accessToken = "com.depart.accessToken"
        static let refreshToken = "com.depart.refreshToken"
        static let userId = "com.depart.userId"
        static let email = "com.depart.email"
        static let password = "com.depart.password"
    }

    init() {}

    /// Set the API client (called during app setup to break circular init).
    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Token Access

    func getAccessToken() -> String? {
        KeychainHelper.readString(key: Keys.accessToken)
    }

    // MARK: - Session Restore

    /// Called on app launch. Checks for existing tokens and attempts to restore session.
    func restoreSession() async {
        guard let _ = KeychainHelper.readString(key: Keys.accessToken),
              let userIdString = KeychainHelper.readString(key: Keys.userId),
              let userId = UUID(uuidString: userIdString)
        else {
            // No existing session — perform invisible registration
            await performInvisibleAuth()
            return
        }

        currentUserId = userId
        isAuthenticated = true

        // Fetch fresh profile
        do {
            userProfile = try await apiClient?.fetchProfile()
        } catch {
            print("[AuthManager] Failed to fetch profile: \(error)")
            // Token may be expired — try refresh
            do {
                try await refreshTokenIfNeeded(force: true)
                userProfile = try await apiClient?.fetchProfile()
            } catch {
                print("[AuthManager] Refresh failed, re-registering: \(error)")
                await performInvisibleAuth()
            }
        }
    }

    // MARK: - Invisible Auto-Registration

    /// Generates a unique email/password and registers with the backend.
    /// The user never sees a sign-up form.
    private func performInvisibleAuth() async {
        // Check if we have stored credentials from a previous registration
        if let email = KeychainHelper.readString(key: Keys.email),
           let password = KeychainHelper.readString(key: Keys.password) {
            // Try logging in with existing credentials
            do {
                let response = try await apiClient?.login(email: email, password: password)
                if let response {
                    handleAuthResponse(response)
                    return
                }
            } catch {
                print("[AuthManager] Login with stored credentials failed: \(error)")
            }
        }

        // Generate new credentials
        let deviceId = UUID().uuidString.lowercased()
        let email = "device-\(deviceId)@depart.local"
        let password = UUID().uuidString // Random 36-char password

        do {
            let timezone = TimeZone.current.identifier
            let response = try await apiClient?.register(
                email: email,
                password: password,
                displayName: nil,
                timezone: timezone
            )

            if let response {
                // Store credentials for future sessions
                try? KeychainHelper.save(key: Keys.email, string: email)
                try? KeychainHelper.save(key: Keys.password, string: password)
                handleAuthResponse(response)
            }
        } catch {
            print("[AuthManager] Invisible registration failed: \(error)")
            // App will work in degraded mode without auth
        }
    }

    // MARK: - Token Refresh

    /// Refresh the access token using the refresh token.
    func refreshTokenIfNeeded(force: Bool = false) async throws {
        guard let refreshToken = KeychainHelper.readString(key: Keys.refreshToken) else {
            throw APIError.unauthorized
        }

        guard let response = try await apiClient?.refreshToken(refreshToken) else {
            throw APIError.unauthorized
        }

        handleAuthResponse(response)
    }

    // MARK: - Logout

    func logout() {
        KeychainHelper.delete(key: Keys.accessToken)
        KeychainHelper.delete(key: Keys.refreshToken)
        KeychainHelper.delete(key: Keys.userId)
        isAuthenticated = false
        currentUserId = nil
        userProfile = nil
    }

    // MARK: - Private

    private func handleAuthResponse(_ response: AuthResponse) {
        try? KeychainHelper.save(key: Keys.accessToken, string: response.accessToken)
        try? KeychainHelper.save(key: Keys.refreshToken, string: response.refreshToken)
        try? KeychainHelper.save(key: Keys.userId, string: response.user.id.uuidString)
        currentUserId = response.user.id
        userProfile = response.user
        isAuthenticated = true
    }
}
