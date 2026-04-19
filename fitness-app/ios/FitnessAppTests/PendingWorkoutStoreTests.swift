import XCTest
@testable import FitnessApp

@MainActor
final class PendingWorkoutStoreTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("PendingWorkoutStoreTests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    // MARK: - Helpers

    private func makeStore() -> PendingWorkoutStore {
        PendingWorkoutStore(directory: tempDir)
    }

    private func sampleWorkout(date: String = "2026-04-19") -> WorkoutCreate {
        WorkoutCreate(
            date: date,
            durationMinutes: 60,
            sessionRpe: 8,
            notes: nil,
            exercises: [
                WorkoutExerciseCreate(
                    exerciseId: "ex-123",
                    orderIndex: 0,
                    sets: [
                        SetCreate(weight: 135.0, weightUnit: "lb", reps: 5, rpe: 8, rir: nil, setNumber: 1)
                    ],
                    supersetGroupId: nil
                )
            ]
        )
    }

    // MARK: - Enqueue

    func testEnqueueAppendsAndPersists() throws {
        let store = makeStore()
        XCTAssertEqual(store.count, 0)

        let entry = store.enqueue(sampleWorkout())

        XCTAssertEqual(store.count, 1)
        XCTAssertEqual(store.pending.first?.id, entry.id)
        XCTAssertEqual(store.pending.first?.workout.date, "2026-04-19")
    }

    func testEnqueueMultipleItemsPreservesFIFOOrder() throws {
        let store = makeStore()

        _ = store.enqueue(sampleWorkout(date: "2026-04-17"))
        _ = store.enqueue(sampleWorkout(date: "2026-04-18"))
        _ = store.enqueue(sampleWorkout(date: "2026-04-19"))

        XCTAssertEqual(store.count, 3)
        XCTAssertEqual(store.pending.map { $0.workout.date }, ["2026-04-17", "2026-04-18", "2026-04-19"])
    }

    // MARK: - Persistence

    func testEntriesPersistAcrossStoreInstances() throws {
        // First store: enqueue.
        let storeA = makeStore()
        _ = storeA.enqueue(sampleWorkout(date: "2026-04-01"))
        _ = storeA.enqueue(sampleWorkout(date: "2026-04-02"))
        XCTAssertEqual(storeA.count, 2)

        // Second store pointing at same directory should load the same entries.
        let storeB = makeStore()
        XCTAssertEqual(storeB.count, 2)
        XCTAssertEqual(storeB.pending.map { $0.workout.date }, ["2026-04-01", "2026-04-02"])
    }

    func testClearAllWipesDisk() throws {
        let storeA = makeStore()
        _ = storeA.enqueue(sampleWorkout())
        storeA.clearAll()
        XCTAssertEqual(storeA.count, 0)

        let storeB = makeStore()
        XCTAssertEqual(storeB.count, 0)
    }

    // MARK: - Remove

    func testRemoveDropsOnlyThatEntry() throws {
        let store = makeStore()
        let a = store.enqueue(sampleWorkout(date: "2026-04-01"))
        let b = store.enqueue(sampleWorkout(date: "2026-04-02"))

        store.remove(id: a.id)

        XCTAssertEqual(store.count, 1)
        XCTAssertEqual(store.pending.first?.id, b.id)
    }

    // MARK: - Stale warning

    func testHasStaleEntriesFalseWhenFresh() throws {
        let store = makeStore()
        _ = store.enqueue(sampleWorkout())

        XCTAssertFalse(store.hasStaleEntries(now: Date()))
        XCTAssertFalse(store.hasStaleWarning)
    }

    func testHasStaleEntriesTrueWhenOlderThanThreshold() throws {
        let store = makeStore()
        _ = store.enqueue(sampleWorkout())

        // Fake "now" 31 days in the future.
        let future = Date().addingTimeInterval(TimeInterval(31 * 24 * 60 * 60))
        XCTAssertTrue(store.hasStaleEntries(now: future))
    }

    func testStaleWarningSurfacesAfterReloadWhenEntryIsOld() throws {
        // Seed disk with a manually backdated entry, then reopen the store to
        // verify the warning flips on.
        let oldDate = Date().addingTimeInterval(-TimeInterval(45 * 24 * 60 * 60))
        let fileURL = tempDir.appendingPathComponent("pending_workouts.json")

        let entry = PendingWorkoutStore.PendingWorkout(
            workout: sampleWorkout(),
            id: UUID(),
            createdAt: oldDate
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode([entry])
        try data.write(to: fileURL)

        let store = makeStore()
        XCTAssertEqual(store.count, 1)
        XCTAssertTrue(store.hasStaleWarning, "Stale warning should flip on after loading a 45-day-old entry")
    }
}
