import Foundation

/// On-disk queue of workouts that failed to POST due to network errors.
///
/// Design:
/// - Persists JSON to `Application Support/pending_workouts.json` so it survives app restarts
/// - Each entry carries a client-generated UUID so the backend can dedupe when we finally upload
///   (TODO: backend must accept a `client_id` field on `WorkoutCreate` and reject duplicates — out
///    of scope for this PR, see PR description)
/// - Drain is serialized through an `actor`-like queue on the main actor to avoid double-sending
/// - Entries older than `staleThresholdDays` surface a warning to the user rather than silently
///   uploading stale data
@MainActor
final class PendingWorkoutStore: ObservableObject {
    static let shared = PendingWorkoutStore()

    // MARK: - Types

    /// A workout queued for later upload.
    /// Wraps `WorkoutCreate` with a client-generated UUID (for backend dedupe) and the
    /// creation timestamp (for stale-data warning).
    struct PendingWorkout: Codable, Identifiable {
        let id: UUID
        let createdAt: Date
        let workout: WorkoutCreate
        /// Number of failed drain attempts. We retain the entry and retry on
        /// future drains up to `maxRetryAttempts` — then drop it so a
        /// permanently-malformed payload doesn't wedge the queue forever.
        var failedAttempts: Int
        /// Human-readable text of the last error this entry hit, if any.
        /// Surfaced in the UI when the entry eventually gets dropped.
        var lastError: String?

        init(
            workout: WorkoutCreate,
            id: UUID = UUID(),
            createdAt: Date = Date(),
            failedAttempts: Int = 0,
            lastError: String? = nil
        ) {
            self.id = id
            self.createdAt = createdAt
            self.workout = workout
            self.failedAttempts = failedAttempts
            self.lastError = lastError
        }

        // Custom decoder so queue files written before `failedAttempts` /
        // `lastError` existed still load cleanly — they default to 0 / nil.
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            self.id = try c.decode(UUID.self, forKey: .id)
            self.createdAt = try c.decode(Date.self, forKey: .createdAt)
            self.workout = try c.decode(WorkoutCreate.self, forKey: .workout)
            self.failedAttempts = try c.decodeIfPresent(Int.self, forKey: .failedAttempts) ?? 0
            self.lastError = try c.decodeIfPresent(String.self, forKey: .lastError)
        }
    }

    /// After this many consecutive failed drain attempts, an entry is
    /// considered poison and dropped. Gives us ~5 independent opportunities
    /// (across app foregrounds / manual retries) before giving up — enough
    /// to ride out a rolling deploy or a multi-minute backend outage.
    static let maxRetryAttempts: Int = 5

    enum DrainResult {
        case success
        case skipped           // Nothing to drain
        case failed(Error)     // Network still down — keep in queue
    }

    // MARK: - Config

    /// Entries older than this (in days) produce a warning on next drain attempt.
    let staleThresholdDays: Int = 30

    // MARK: - Published state

    @Published private(set) var pending: [PendingWorkout] = []
    @Published private(set) var hasStaleWarning: Bool = false
    @Published private(set) var lastDrainError: String?

    // MARK: - Internals

    private let fileURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private var isDraining = false

    /// Inject a custom directory (used by tests) or default to Application Support.
    init(directory: URL? = nil) {
        let baseDir: URL
        if let directory = directory {
            baseDir = directory
        } else {
            // Application Support is not created by default on iOS — ensure it exists.
            let fm = FileManager.default
            let appSupport = (try? fm.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true
            )) ?? fm.temporaryDirectory
            baseDir = appSupport
        }

        try? FileManager.default.createDirectory(at: baseDir, withIntermediateDirectories: true)
        self.fileURL = baseDir.appendingPathComponent("pending_workouts.json")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder

        loadFromDisk()
        refreshStaleWarning()
    }

    // MARK: - Public API

    /// Current queue length.
    var count: Int { pending.count }

    /// Add a workout to the queue and persist to disk.
    @discardableResult
    func enqueue(_ workout: WorkoutCreate) -> PendingWorkout {
        let entry = PendingWorkout(workout: workout)
        pending.append(entry)
        saveToDisk()
        refreshStaleWarning()
        return entry
    }

    /// Drop everything from the queue. Used after a successful manual save or for testing.
    func clearAll() {
        pending.removeAll()
        saveToDisk()
        refreshStaleWarning()
    }

    /// Remove a specific pending entry (after successful upload).
    func remove(id: UUID) {
        pending.removeAll { $0.id == id }
        saveToDisk()
        refreshStaleWarning()
    }

    /// Attempt to upload every queued workout, in FIFO order.
    ///
    /// Policy per failure mode:
    /// - `.networkError` / `.unauthorized` / `.serviceUnavailable` / `.rateLimited`
    ///   / `.serverError`: keep the entry, stop draining, surface the error. A
    ///   future drain will retry.
    /// - `.badRequest` / `.validationError` / other client-side 4xx: the payload
    ///   is almost certainly malformed. Increment `failedAttempts`; drop only
    ///   after `maxRetryAttempts` to avoid wedging on a single bad entry but
    ///   also to avoid silently losing data on a transient server-side bug
    ///   that happens to surface as a 4xx.
    ///
    /// Returns `.success` if the queue drained (or was already empty),
    /// `.failed(error)` if a recoverable error blocked draining.
    @discardableResult
    func drain(api: APIClient = APIClient.shared) async -> DrainResult {
        guard !isDraining else { return .skipped }
        guard !pending.isEmpty else { return .skipped }
        isDraining = true
        defer { isDraining = false }

        lastDrainError = nil

        // Snapshot the current list — we modify `pending` as we go.
        let snapshot = pending

        for entry in snapshot {
            do {
                // Use the XP-aware endpoint so the server awards XP, PRs,
                // achievements, quest credit, and dungeon progress for the
                // drained workout. The bare `createWorkout` path skips all of
                // that, silently losing every reward for offline-queued work.
                //
                // We intentionally discard the `WorkoutCreateResponse` payload
                // here — the UI isn't active during a background drain, so
                // there's nothing to celebrate against. HomeView refetches
                // `/users/progress` (see HomeViewModel.loadData) every time it
                // appears / foregrounds, so the authoritative XP + level +
                // streak come back from the server on the next surface view.
                _ = try await api.createWorkoutWithXP(entry.workout)
                // Uploaded OK — remove from queue
                remove(id: entry.id)
            } catch let apiError as APIError {
                switch apiError {
                case .networkError, .unauthorized,
                     .serviceUnavailable, .rateLimited, .serverError:
                    // Transient — keep the entry, stop the drain, retry next time.
                    // Server outages, rolling deploys, auth refreshes, and 5xx
                    // all fall here. Dropping the entry would be data loss.
                    lastDrainError = apiError.localizedDescription
                    return .failed(apiError)
                default:
                    // Likely-malformed payload (400/422). Count this as a
                    // failed attempt and only drop once we've exceeded the
                    // retry budget — some 4xx are actually transient server
                    // bugs in disguise.
                    bumpAttempt(entryId: entry.id, error: apiError.localizedDescription)
                }
            } catch {
                // Unknown error shape — treat as transient and keep the entry.
                lastDrainError = error.localizedDescription
                return .failed(error)
            }
        }

        refreshStaleWarning()
        return .success
    }

    /// Increment the failed-attempt counter for a queued entry, and drop it
    /// if we've hit the retry budget. Persists either way.
    private func bumpAttempt(entryId: UUID, error: String) {
        guard let idx = pending.firstIndex(where: { $0.id == entryId }) else { return }
        pending[idx].failedAttempts += 1
        pending[idx].lastError = error
        if pending[idx].failedAttempts >= Self.maxRetryAttempts {
            lastDrainError = "Dropped pending workout after \(Self.maxRetryAttempts) attempts: \(error)"
            pending.remove(at: idx)
        } else {
            lastDrainError = "Retrying pending workout (attempt \(pending[idx].failedAttempts) of \(Self.maxRetryAttempts)): \(error)"
        }
        saveToDisk()
    }

    /// Whether any queued entry is older than `staleThresholdDays`.
    func hasStaleEntries(now: Date = Date()) -> Bool {
        let threshold = TimeInterval(staleThresholdDays * 24 * 60 * 60)
        return pending.contains { now.timeIntervalSince($0.createdAt) > threshold }
    }

    // MARK: - Persistence

    private func loadFromDisk() {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        do {
            let data = try Data(contentsOf: fileURL)
            pending = try decoder.decode([PendingWorkout].self, from: data)
        } catch {
            #if DEBUG
            print("DEBUG: PendingWorkoutStore failed to load: \(error)")
            #endif
            pending = []
        }
    }

    private func saveToDisk() {
        do {
            let data = try encoder.encode(pending)
            // `.completeFileProtectionUntilFirstUserAuthentication` encrypts
            // the file at rest but allows reads and writes once the user has
            // unlocked the device for the first time after boot. Critically,
            // this lets the background drain (triggered by scene-phase /
            // remote push wakeups) persist successful uploads or retry
            // bookkeeping even if the device has since re-locked.
            // `.completeFileProtection` would reject those writes and cause
            // data loss. Queued WorkoutCreate payloads are identity-linked
            // but not credentials, so the slightly weaker protection class
            // is the right tradeoff.
            try data.write(
                to: fileURL,
                options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]
            )
        } catch {
            #if DEBUG
            print("DEBUG: PendingWorkoutStore failed to save: \(error)")
            #endif
        }
    }

    private func refreshStaleWarning() {
        hasStaleWarning = hasStaleEntries()
    }
}
