import Foundation

/// On-disk copy of the hunt in progress, so a crash, force quit or memory
/// kill mid-session costs nothing.
///
/// Design:
/// - One JSON file, `Application Support/hunt_draft.json`. A draft either
///   exists or it doesn't; there is only ever one hunt in progress.
/// - `LogViewModel` writes it half a second after the last edit, flushes it
///   when the app leaves the foreground, restores it on creation, and clears
///   it the moment the hunt is saved, queued offline or abandoned.
/// - An unreadable file (format drift, truncated write) reads as "no draft"
///   and is removed, so it can't fail every launch.
@MainActor
final class HuntDraftStore {
    static let shared = HuntDraftStore()

    private let fileURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

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
        self.fileURL = baseDir.appendingPathComponent("hunt_draft.json")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    /// Whether a draft file is on disk.
    var hasDraft: Bool {
        FileManager.default.fileExists(atPath: fileURL.path)
    }

    /// The saved hunt, or nil when there is none or it can't be read.
    func load() -> HuntDraft? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        guard let draft = try? decoder.decode(HuntDraft.self, from: data) else {
            clear()
            return nil
        }
        return draft
    }

    /// Replace the draft on disk. Atomic, so a kill mid-write leaves the
    /// previous draft rather than a torn file.
    func save(_ draft: HuntDraft) {
        guard let data = try? encoder.encode(draft) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }

    /// Remove the draft. Safe to call when there is none.
    func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }
}

/// Snapshot of an in-progress hunt — `LogViewModel`'s editable state.
struct HuntDraft: Codable {
    var date: Date
    var name: String
    var notes: String
    var sessionRPE: Int?
    var exercises: [LoggedExercise]
    /// When the hunt timer started, so the elapsed time survives a relaunch.
    var startedAt: Date?
    var updatedAt: Date
}
