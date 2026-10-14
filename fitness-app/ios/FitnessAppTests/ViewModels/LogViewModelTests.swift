import SwiftUI
import XCTest
@testable import FitnessApp

/// Regression tests for the hunt-submit crash.
///
/// The active-hunt rows bind into `LogViewModel.selectedExercises`, and
/// submitting a hunt resets that array to `[]` while the rows are still
/// mounted (under the XP cover, and on the offline-queue fallback). The
/// index-based bindings that used to live there trapped with "Index out of
/// range" — worst in superset rounds, whose binding went two indices deep.
/// These pin the by-id `Binding.element(matching:)` that replaced them and
/// the guarded, index-taking row actions on the view model.
@MainActor
final class LogViewModelTests: XCTestCase {

    // MARK: - Helpers

    private func loggedExercise(
        _ exerciseId: String,
        name: String,
        setCount: Int = 1,
        group: UUID? = nil
    ) -> LoggedExercise {
        LoggedExercise(
            exerciseId: exerciseId,
            exerciseName: name,
            sets: (1...setCount).map { LoggedSet(setNumber: $0) },
            supersetGroupId: group
        )
    }

    // MARK: - Binding.element(matching:)

    func testElementBindingReadsAndWritesTheMatchingElement() {
        var sets = [LoggedSet(setNumber: 1), LoggedSet(setNumber: 2)]
        let all = Binding(get: { sets }, set: { sets = $0 })

        let row = all.element(matching: sets[1])
        XCTAssertEqual(row.wrappedValue.setNumber, 2)

        row.wrappedValue.repsText = "8"
        XCTAssertEqual(sets[1].repsText, "8")
        XCTAssertEqual(sets[0].repsText, "", "Only the matching element is written")
    }

    func testElementBindingSurvivesItsElementBeingRemoved() {
        var sets = [LoggedSet(setNumber: 1), LoggedSet(setNumber: 2)]
        let all = Binding(get: { sets }, set: { sets = $0 })
        let row = all.element(matching: sets[1])

        // What resetWorkout() does under a still-mounted row.
        sets = []

        // A read falls back to the row's snapshot instead of trapping.
        XCTAssertEqual(row.wrappedValue.setNumber, 2)

        // A write to a removed element is dropped, not applied out of range.
        row.wrappedValue.repsText = "8"
        XCTAssertTrue(sets.isEmpty)
    }

    /// The superset round path: `$allExercises.element(matching: exercise)
    /// .sets.element(matching: set)` — the two-level binding that trapped
    /// on every submit of an all-superset hunt.
    func testNestedElementBindingMatchesTheSupersetRoundPath() {
        let group = UUID()
        var exercises = [
            loggedExercise("curl", name: "Curl", setCount: 2, group: group),
            loggedExercise("row", name: "Row", setCount: 2, group: group),
        ]
        let all = Binding(get: { exercises }, set: { exercises = $0 })

        let snapshot = exercises[1]
        let round2 = all.element(matching: snapshot).sets.element(matching: snapshot.sets[1])

        round2.wrappedValue.weightText = "95"
        XCTAssertEqual(exercises[1].sets[1].weightText, "95")
        XCTAssertEqual(exercises[1].sets[0].weightText, "")
        XCTAssertEqual(exercises[0].sets[1].weightText, "")

        // Hunt submitted → the list is emptied while the round is mounted.
        exercises = []
        XCTAssertEqual(round2.wrappedValue.setNumber, 2)
        round2.wrappedValue.weightText = "100"
        XCTAssertTrue(exercises.isEmpty)
    }

    // MARK: - Row actions after a reset

    func testRowActionsIgnoreAStaleIndexAfterReset() {
        let viewModel = LogViewModel()
        viewModel.selectedExercises = [loggedExercise("squat", name: "Squat")]
        viewModel.resetWorkout()

        // Indices captured by the last render of the now-removed rows.
        viewModel.addSet(to: 0)
        viewModel.copyLastSet(for: 0)
        viewModel.removeSet(from: 0, at: 0)
        viewModel.removeExercise(at: 0)

        XCTAssertTrue(viewModel.selectedExercises.isEmpty)
    }

    func testRemoveSetIgnoresAnOutOfRangeSetIndex() {
        let viewModel = LogViewModel()
        viewModel.selectedExercises = [loggedExercise("squat", name: "Squat", setCount: 2)]

        viewModel.removeSet(from: 0, at: 5)
        XCTAssertEqual(viewModel.selectedExercises[0].sets.count, 2)

        viewModel.removeSet(from: 0, at: 0)
        XCTAssertEqual(viewModel.selectedExercises[0].sets.map(\.setNumber), [1], "Remaining sets are renumbered")
    }

    // MARK: - Superset grouping

    func testSupersetRowsGroupByIdAndSinglesKeepTheirIndex() {
        let viewModel = LogViewModel()
        let group = UUID()
        viewModel.selectedExercises = [
            loggedExercise("curl", name: "Curl", group: group),
            loggedExercise("row", name: "Row", group: group),
            loggedExercise("squat", name: "Squat"),
        ]

        let items = viewModel.exercisesGroupedForDisplay
        XCTAssertEqual(items.count, 2)

        guard case .superset(let groupId, let exercises) = items[0] else {
            XCTFail("Expected the superset first")
            return
        }
        XCTAssertEqual(groupId, group)
        XCTAssertEqual(exercises.map(\.exerciseId), ["curl", "row"])

        guard case .single(let single, let index) = items[1] else {
            XCTFail("Expected the single exercise second")
            return
        }
        XCTAssertEqual(single.exerciseId, "squat")
        XCTAssertEqual(index, 2)
    }

    func testSupersetRoundActionsTouchOnlyTheGroup() {
        let viewModel = LogViewModel()
        let group = UUID()
        viewModel.selectedExercises = [
            loggedExercise("curl", name: "Curl", group: group),
            loggedExercise("row", name: "Row", group: group),
            loggedExercise("squat", name: "Squat"),
        ]

        viewModel.addRoundToSuperset(groupId: group)
        XCTAssertEqual(viewModel.selectedExercises.map { $0.sets.count }, [2, 2, 1])

        viewModel.selectedExercises[0].sets[1].repsText = "10"
        viewModel.copyLastRoundToSuperset(groupId: group)
        XCTAssertEqual(viewModel.selectedExercises.map { $0.sets.count }, [3, 3, 1])
        XCTAssertEqual(viewModel.selectedExercises[0].sets[2].repsText, "10")
        XCTAssertEqual(viewModel.selectedExercises[0].sets[2].setNumber, 3)

        viewModel.removeSuperset(groupId: group)
        XCTAssertEqual(viewModel.selectedExercises.map(\.exerciseId), ["squat"])
    }
}
