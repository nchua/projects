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

        init(workout: WorkoutCreate, id: UUID = UUID(), createdAt: Date = Date()) {
            self.id = id
            self.createdAt = createdAt
            self.workout = workout
        }
    }

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
    /// Returns `.success` if the queue drained (or was already empty),
    /// `.failed(error)` if a network error blocked draining.
    /// Client/auth errors do NOT stop the drain — they drop the bad entry
    /// so we don't get stuck forever on malformed data.
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
                _ = try await api.createWorkout(entry.workout)
                // Uploaded OK — remove from queue
                remove(id: entry.id)
            } catch let apiError as APIError {
                switch apiError {
                case .networkError:
                    // Still offline — stop here, keep remaining entries in queue.
                    lastDrainError = apiError.localizedDescription
                    return .failed(apiError)
                case .unauthorized:
                    // Don't drop the entry — the caller will re-authenticate and retry.
                    lastDrainError = apiError.localizedDescription
                    return .failed(apiError)
                default:
                    // 4xx/5xx that isn't a network problem — the payload is likely bad.
                    // Drop it so we don't get wedged on a single poison entry, but
                    // surface the error to the user.
                    lastDrainError = "Skipped pending workout: \(apiError.localizedDescription)"
                    remove(id: entry.id)
                }
            } catch {
                lastDrainError = error.localizedDescription
                return .failed(error)
            }
        }

        refreshStaleWarning()
        return .success
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
            try data.write(to: fileURL, options: [.atomic])
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
