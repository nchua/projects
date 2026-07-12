import Foundation
import UIKit

/// Backs the WHOOP row in Hunter › Integrations (stub until ARISE v2.1).
///
/// Connect flow: `GET /whoop/connect` → open the authorize URL in the system
/// browser → WHOOP redirects to the backend callback page → the user returns
/// to the app and `load()` re-reads `/whoop/status` on the next appear.
@MainActor
final class WhoopConnectionViewModel: ObservableObject {
    /// Backend has WHOOP OAuth credentials configured (not whether *this* user is connected).
    @Published private(set) var configured = false
    @Published private(set) var connected = false
    @Published private(set) var isConnecting = false

    func load() async {
        guard let status = try? await APIClient.shared.getWhoopStatus() else { return }
        configured = status.configured
        connected = status.connected
        if connected {
            _ = await WhoopAutoSync.syncIfDue()
        }
    }

    func connect() async {
        guard configured, !connected, !isConnecting else { return }
        isConnecting = true
        defer { isConnecting = false }
        guard let response = try? await APIClient.shared.getWhoopConnect(),
              let url = URL(string: response.authorizeUrl) else { return }
        await UIApplication.shared.open(url)
    }
}

/// Fire-and-forget WHOOP pull (workout HR backfill + recovery/sleep rows that
/// feed Condition), throttled so app-open spam doesn't hammer the WHOOP API.
enum WhoopAutoSync {
    private static let throttleKey = "whoopLastAutoSyncAt"
    private static let minInterval: TimeInterval = 4 * 3600

    /// Returns true when a sync was actually attempted, so the caller can
    /// refresh Condition with the fresh recovery inputs.
    static func syncIfDue() async -> Bool {
        let last = UserDefaults.standard.double(forKey: throttleKey)
        guard Date().timeIntervalSince1970 - last >= minInterval else { return false }
        guard let status = try? await APIClient.shared.getWhoopStatus(),
              status.connected else { return false }
        // The 10s client timeout can cut a slow sync short — the server still
        // finishes and commits, so a timeout here still counts as an attempt.
        _ = try? await APIClient.shared.postWhoopSync(days: 7)
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: throttleKey)
        return true
    }
}
