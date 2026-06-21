import Foundation

/// Funnels foreground sync work so the silent HealthKit workout import doesn't fight the
/// existing daily activity sync (`HealthKitManager.syncTodayOnly`). Owns the debounce +
/// in-flight guard for the single global `scenePhase → .active` observer in `FitnessApp`.
@MainActor
final class SyncCoordinator: ObservableObject {
    static let shared = SyncCoordinator()

    @Published private(set) var isRunning = false

    private var lastForegroundSyncAt: Date?
    /// Skip foreground imports that fire within this window of the last one (Control Center
    /// pulls, post-permission-sheet returns, rapid app switches all re-fire `.active`).
    private let debounceInterval: TimeInterval = 5 * 60 // 5 minutes

    private init() {}

    /// Called on every `scenePhase == .active`. Silently imports new Apple-Watch workouts —
    /// no toast/alert/notification. Never prompts for HealthKit permission (that only happens
    /// from the settings "Connect Apple Health" action); if permission hasn't been granted yet
    /// the underlying import early-returns harmlessly.
    func syncOnForeground() async {
        guard AuthManager.shared.isAuthenticated else { return }
        guard HealthKitManager.shared.isHealthDataAvailable else { return }

        if let last = lastForegroundSyncAt, Date().timeIntervalSince(last) < debounceInterval {
            return
        }
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }
        lastForegroundSyncAt = Date()

        // HealthKitManager doesn't hold the profile; pass age in for the 220−age zones.
        let age = await currentAge()
        await HealthKitManager.shared.importNewWorkouts(age: age)
    }

    private func currentAge() async -> Int? {
        do {
            return try await APIClient.shared.getProfile().age
        } catch {
            return nil // age unknown → import still proceeds, just without HR zones
        }
    }
}
