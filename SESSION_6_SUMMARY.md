# Session 6 Summary - iOS Session Expiry Fix

**Date:** January 2, 2026

## Issue

When the user's authentication token expired:
1. The Hunter (Profile) screen showed "session expired" but stayed on a loading state
2. The Stats screen didn't load any data
3. Users were stuck and couldn't log out to re-authenticate

## Root Cause

The iOS app had no mechanism to automatically redirect users to the login screen when their session expired. When the API returned a 401 Unauthorized error:
1. `APIClient` tried to refresh the token
2. If refresh failed, it threw `APIError.unauthorized`
3. ViewModels caught the error and showed an error message
4. But `AuthManager.isAuthenticated` remained `true`
5. User stayed on the main app screens in a broken state

## Solution

### 1. APIClient.swift - Added session expiry callback

```swift
/// Callback for when session expires and user needs to re-authenticate
var onSessionExpired: (() -> Void)?

// In the request method, when 401 occurs and refresh fails:
case 401:
    if !isRetry, refreshToken != nil {
        do {
            _ = try await refreshAccessToken()
            return try await self.request(...)
        } catch {
            // Refresh failed - notify app to redirect to login
            DispatchQueue.main.async {
                self.onSessionExpired?()
            }
            throw APIError.unauthorized
        }
    }
    // No refresh token or already retried
    DispatchQueue.main.async {
        self.onSessionExpired?()
    }
    throw APIError.unauthorized
```

### 2. AuthManager.swift - Auto-logout on session expiry

```swift
private init() {
    // ... existing init code ...

    // Listen for session expiry from APIClient
    APIClient.shared.onSessionExpired = { [weak self] in
        self?.handleSessionExpired()
    }
}

private func handleSessionExpired() {
    logout()
    error = "Session expired. Please sign in again."
}
```

### 3. All ViewModels - Don't show error dialogs for unauthorized

Updated all ViewModels to not display error alerts for `APIError.unauthorized` since the user will be automatically redirected to login:

```swift
} catch let apiError as APIError {
    // Don't set error for unauthorized - user will be redirected to login
    if case .unauthorized = apiError { return }
    self.error = apiError.localizedDescription
} catch {
    self.error = error.localizedDescription
}
```

**Files modified:**
- `HomeViewModel.swift`
- `ProfileViewModel.swift`
- `ProgressViewModel.swift`
- `HistoryViewModel.swift`

## How It Works Now

1. User opens app with expired token
2. Any API call fails with 401
3. APIClient tries to refresh token → fails
4. `onSessionExpired` callback triggers `AuthManager.logout()`
5. `isAuthenticated` becomes `false`
6. `ContentView` shows login screen with message "Session expired. Please sign in again."

## Lesson Learned

**Always implement global auth state management for session expiry.**

When building apps with token-based authentication:
1. Don't just throw errors for 401 responses - handle them globally
2. Use a callback/notification pattern to decouple APIClient from AuthManager
3. Set `isAuthenticated = false` when tokens are invalid, not just when user explicitly logs out
4. ViewModels should gracefully handle auth errors without showing confusing UI

## Prevention Checklist

For future iOS apps with authentication:
- [ ] APIClient has a session expiry callback/notification
- [ ] AuthManager listens for session expiry and updates auth state
- [ ] ContentView/root view observes auth state and shows login when needed
- [ ] ViewModels don't show error dialogs for auth failures (redirect handles it)
- [ ] Test the flow: expire a token manually and verify redirect works
