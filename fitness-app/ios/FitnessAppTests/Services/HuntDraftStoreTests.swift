import XCTest
@testable import FitnessApp

@MainActor
final class HuntDraftStoreTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("HuntDraftStoreTests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    // MARK: - Helpers

    private func makeStore() -> HuntDraftStore {
        HuntDraftStore(directory: tempDir)
    }

    /// A superset plus a single, with the field shapes the Log view produces.
    private func sampleDraft() -> HuntDraft {
        let group = UUID()
        return HuntDraft(
            date: Date(timeIntervalSince1970: 1_760_000_000),
            name: "Pull Day",
            notes: "Felt strong",
            sessionRPE: 8,
            exercises: [
                LoggedExercise(
                    exerciseId: "row",
                    exerciseName: "Row",
                    primaryMuscle: "Back",
                    sets: [
                        LoggedSet(setNumber: 1, weightText: "135", repsText: "8", rpe: 7, isBodyweight: false),
                        LoggedSet(setNumber: 2, weightText: "145", repsText: "6", rpe: nil, isBodyweight: false),
                    ],
                    supersetGroupId: group
                ),
                LoggedExercise(
                    exerciseId: "pullup",
                    exerciseName: "Pull-Up",
                    sets: [LoggedSet(setNumber: 1, weightText: "", repsText: "10", rpe: nil, isBodyweight: true)],
                    supersetGroupId: group
                ),
                LoggedExercise(exerciseId: "curl", exerciseName: "Curl", sets: [LoggedSet(setNumber: 1)]),
            ],
            startedAt: Date(timeIntervalSince1970: 1_760_000_000),
            updatedAt: Date(timeIntervalSince1970: 1_760_000_600)
        )
    }

    // MARK: - Tests

    func testLoadWithoutAFileIsNil() {
        let store = makeStore()
        XCTAssertFalse(store.hasDraft)
        XCTAssertNil(store.load())
    }

    func testSaveThenLoadRoundTripsTheHunt() throws {
        let store = makeStore()
        let draft = sampleDraft()
        store.save(draft)
        XCTAssertTrue(store.hasDraft)

        // A fresh store over the same directory is what a relaunch sees.
        let loaded = try XCTUnwrap(makeStore().load())
        XCTAssertEqual(loaded.name, "Pull Day")
        XCTAssertEqual(loaded.notes, "Felt strong")
        XCTAssertEqual(loaded.sessionRPE, 8)
        XCTAssertEqual(loaded.date.timeIntervalSince1970, draft.date.timeIntervalSince1970, accuracy: 1)
        XCTAssertEqual(loaded.startedAt?.timeIntervalSince1970 ?? 0, 1_760_000_000, accuracy: 1)

        XCTAssertEqual(loaded.exercises.map(\.exerciseId), ["row", "pullup", "curl"])
        XCTAssertEqual(loaded.exercises[0].exerciseName, "Row")
        XCTAssertEqual(loaded.exercises[0].primaryMuscle, "Back")
        XCTAssertEqual(loaded.exercises[0].sets.map(\.setNumber), [1, 2])
        XCTAssertEqual(loaded.exercises[0].sets.map(\.weightText), ["135", "145"])
        XCTAssertEqual(loaded.exercises[0].sets.map(\.repsText), ["8", "6"])
        XCTAssertEqual(loaded.exercises[0].sets.map(\.rpe), [7, nil])
        XCTAssertTrue(loaded.exercises[1].sets[0].isBodyweight)

        XCTAssertNotNil(loaded.exercises[0].supersetGroupId)
        XCTAssertEqual(
            loaded.exercises[0].supersetGroupId, loaded.exercises[1].supersetGroupId,
            "The superset comes back as one group"
        )
        XCTAssertNil(loaded.exercises[2].supersetGroupId)
    }

    func testClearRemovesTheDraft() {
        let store = makeStore()
        store.save(sampleDraft())
        XCTAssertTrue(store.hasDraft)

        store.clear()
        XCTAssertFalse(store.hasDraft)
        XCTAssertNil(store.load())
    }

    func testCorruptFileReadsAsNoDraftAndIsDropped() throws {
        let store = makeStore()
        try Data("not json".utf8).write(to: tempDir.appendingPathComponent("hunt_draft.json"))

        XCTAssertNil(store.load())
        XCTAssertFalse(store.hasDraft, "An unreadable draft is removed so it can't fail every launch")
    }
}
