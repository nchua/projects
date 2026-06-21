import Foundation

/// Stub view model backing the disabled "Connect WHOOP — coming soon" settings row.
///
/// v1 keeps the row visibly disabled regardless of status (WHOOP connect/attach is out of
/// scope until Railway `WHOOP_*` creds + an approved dev app exist). It still loads
/// `getWhoopStatus()` so the contract is exercised and the row can light up in a later chunk.
@MainActor
final class WhoopConnectionViewModel: ObservableObject {
    /// Backend has WHOOP OAuth credentials configured (not whether *this* user is connected).
    @Published private(set) var configured = false
    @Published private(set) var connected = false

    func load() async {
        guard let status = try? await APIClient.shared.getWhoopStatus() else { return }
        configured = status.configured
        connected = status.connected
    }
}
