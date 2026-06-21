import Foundation

/// UserDefaults-backed persistence for HealthKit workout-import bookkeeping.
///
/// Deliberately kept out of the SwiftData schema — this is sync state (a cursor + a
/// dedup set), not domain data. Backend `/workouts/import-healthkit` is idempotent
/// (dedups by `hk_uuid`), so a missed local dedup only risks a harmless re-POST; this
/// store exists to keep the on-device payloads small, not to be the source of truth.
@MainActor
final class WorkoutImportStore {
    static let shared = WorkoutImportStore()

    private let defaults: UserDefaults
    private let cursorKey = "healthkit.lastWorkoutImportDate"
    private let importedUUIDsKey = "healthkit.importedWorkoutUUIDs"

    /// Cap on the retained UUID set so UserDefaults can't grow unbounded over years of
    /// workouts. Dropping the oldest UUIDs is safe (the backend is idempotent).
    private let maxRetainedUUIDs = 500

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    // MARK: - Cursor

    /// Timestamp of the last successful import run. `nil` on first run, where the caller
    /// defaults the query window to ~30 days ago. Also surfaced as "last imported" in settings.
    var lastWorkoutImportDate: Date? {
        get { defaults.object(forKey: cursorKey) as? Date }
        set { defaults.set(newValue, forKey: cursorKey) }
    }

    func advanceCursor(to date: Date) {
        lastWorkoutImportDate = date
    }

    // MARK: - Dedup set

    /// Already-sent `hk_uuid`s in insertion order (oldest first), capped at `maxRetainedUUIDs`.
    private var importedUUIDOrder: [String] {
        get { defaults.stringArray(forKey: importedUUIDsKey) ?? [] }
        set { defaults.set(newValue, forKey: importedUUIDsKey) }
    }

    /// Whether this `hk_uuid` has already been POSTed in a prior run.
    func isImported(_ hkUuid: String) -> Bool {
        importedUUIDOrder.contains(hkUuid)
    }

    /// Union new uuids into the retained set, preserving insertion order and enforcing the cap.
    func markImported(_ hkUuids: [String]) {
        guard !hkUuids.isEmpty else { return }
        var order = importedUUIDOrder
        var known = Set(order)
        for uuid in hkUuids where !known.contains(uuid) {
            order.append(uuid)
            known.insert(uuid)
        }
        if order.count > maxRetainedUUIDs {
            order.removeFirst(order.count - maxRetainedUUIDs)
        }
        importedUUIDOrder = order
    }

    #if DEBUG
    /// Test/dev helper: forget the cursor + dedup set so the next import re-scans from scratch.
    func reset() {
        defaults.removeObject(forKey: cursorKey)
        defaults.removeObject(forKey: importedUUIDsKey)
    }
    #endif
}
