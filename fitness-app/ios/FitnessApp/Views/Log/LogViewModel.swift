import Foundation
import SwiftUI

@MainActor
class LogViewModel: ObservableObject {
    @Published var exercises: [ExerciseResponse] = []
    @Published var selectedExercises: [LoggedExercise] = []
    @Published var workoutDate = Date()
    @Published var workoutNotes = ""
    @Published var sessionRPE: Int?
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var error: String?
    @Published var showExercisePicker = false
    @Published var searchText = ""
    @Published var selectedCategory: String?
    @Published var workoutSaved = false
    @Published var xpRewardResponse: WorkoutCreateResponse?

    // Offline queue — observed by LogView to render the pending badge.
    let pendingStore = PendingWorkoutStore.shared
    @Published var pendingCount: Int = 0
    @Published var pendingStaleWarning: Bool = false
    @Published var queuedForLater: Bool = false  // Set after a save falls back to the queue
    @Published var isRetryingPending: Bool = false

    var filteredExercises: [ExerciseResponse] {
        var result = exercises

        if let category = selectedCategory {
            result = result.filter { $0.category == category }
        }

        if !searchText.isEmpty {
            result = result.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }

        return result
    }

    var categories: [String] {
        Array(Set(exercises.compactMap { $0.category })).sorted()
    }

    var canSave: Bool {
        !selectedExercises.isEmpty && selectedExercises.allSatisfy { exercise in
            !exercise.sets.isEmpty && exercise.sets.allSatisfy { set in
                (set.isBodyweight || set.weight > 0) && set.reps > 0
            }
        }
    }

    var totalCompletedSets: Int {
        selectedExercises.reduce(0) { total, exercise in
            total + exercise.sets.filter { ($0.isBodyweight || $0.weight > 0) && $0.reps > 0 }.count
        }
    }

    func loadExercises() async {
        isLoading = true
        error = nil

        do {
            exercises = try await APIClient.shared.getExercises()
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func addExercise(_ exercise: ExerciseResponse) {
        let logged = LoggedExercise(
            exerciseId: exercise.id,
            exerciseName: exercise.name,
            sets: [LoggedSet(setNumber: 1)]
        )
        selectedExercises.append(logged)
        showExercisePicker = false
    }

    // MARK: - Superset Methods

    /// Creates a superset from multiple exercises with a shared group ID
    func createSuperset(with exercises: [ExerciseResponse]) {
        guard exercises.count >= 2 else { return }

        let groupId = UUID()
        for exercise in exercises {
            let logged = LoggedExercise(
                exerciseId: exercise.id,
                exerciseName: exercise.name,
                sets: [LoggedSet(setNumber: 1)],
                supersetGroupId: groupId
            )
            selectedExercises.append(logged)
        }
    }

    /// Adds a round (set) to all exercises in a superset group
    func addRoundToSuperset(groupId: UUID) {
        for i in 0..<selectedExercises.count {
            if selectedExercises[i].supersetGroupId == groupId {
                let nextSetNumber = selectedExercises[i].sets.count + 1
                selectedExercises[i].sets.append(LoggedSet(setNumber: nextSetNumber))
            }
        }
    }

    /// Copies the last round's values into a new round for all exercises in a superset group
    func copyLastRoundToSuperset(groupId: UUID) {
        for i in 0..<selectedExercises.count {
            if selectedExercises[i].supersetGroupId == groupId {
                guard let lastSet = selectedExercises[i].sets.last else { continue }
                selectedExercises[i].sets.append(lastSet.copyForNextSet())
            }
        }
    }

    /// Removes all exercises in a superset group
    func removeSuperset(groupId: UUID) {
        selectedExercises.removeAll { $0.supersetGroupId == groupId }
    }

    /// Groups exercises for display - supersets are grouped together
    var exercisesGroupedForDisplay: [ExerciseDisplayItem] {
        var result: [ExerciseDisplayItem] = []
        var processedGroupIds: Set<UUID> = []

        for (index, exercise) in selectedExercises.enumerated() {
            if let groupId = exercise.supersetGroupId {
                // Skip if we've already processed this superset
                if processedGroupIds.contains(groupId) { continue }
                processedGroupIds.insert(groupId)

                // Find all exercises in this superset
                let supersetExercises = selectedExercises.enumerated().filter {
                    $0.element.supersetGroupId == groupId
                }
                let indices = supersetExercises.map { $0.offset }
                let exercises = supersetExercises.map { $0.element }

                result.append(.superset(groupId: groupId, exercises: exercises, indices: indices))
            } else {
                // Regular single exercise
                result.append(.single(exercise: exercise, index: index))
            }
        }
        return result
    }

    func removeExercise(at index: Int) {
        selectedExercises.remove(at: index)
    }

    func addSet(to exerciseIndex: Int) {
        let nextSetNumber = selectedExercises[exerciseIndex].sets.count + 1
        selectedExercises[exerciseIndex].sets.append(LoggedSet(setNumber: nextSetNumber))
    }

    func removeSet(from exerciseIndex: Int, at setIndex: Int) {
        selectedExercises[exerciseIndex].sets.remove(at: setIndex)
        // Renumber sets
        for i in 0..<selectedExercises[exerciseIndex].sets.count {
            selectedExercises[exerciseIndex].sets[i].setNumber = i + 1
        }
    }

    func copyLastSet(for exerciseIndex: Int) {
        guard let lastSet = selectedExercises[exerciseIndex].sets.last else { return }
        selectedExercises[exerciseIndex].sets.append(lastSet.copyForNextSet())
    }

    func saveWorkout() async {
        guard canSave else { return }

        isSaving = true
        error = nil
        queuedForLater = false

        // Use local timezone DateFormatter to ensure the date matches user's local date
        // ISO8601DateFormatter converts to UTC which can shift the date for users in timezones ahead of UTC

        let workoutExercises = selectedExercises.enumerated().map { index, exercise in
            WorkoutExerciseCreate(
                exerciseId: exercise.exerciseId,
                orderIndex: index,
                sets: exercise.sets.map { set in
                    SetCreate(
                        weight: set.weight,
                        weightUnit: "lb",
                        reps: set.reps,
                        rpe: set.rpe,
                        rir: nil,
                        setNumber: set.setNumber
                    )
                },
                supersetGroupId: exercise.supersetGroupId?.uuidString
            )
        }

        let workout = WorkoutCreate(
            date: DateFormatter.localDate.string(from: workoutDate),
            durationMinutes: nil,
            sessionRpe: sessionRPE,
            notes: workoutNotes.isEmpty ? nil : workoutNotes,
            exercises: workoutExercises
        )

        do {
            let response = try await APIClient.shared.createWorkoutWithXP(workout)
            xpRewardResponse = response
            workoutSaved = true
            // Successful network call — also attempt to drain any previously-queued workouts.
            Task { await retryPendingWorkouts(silent: true) }
            // Don't reset yet - wait for XP popup dismissal
        } catch let apiError as APIError {
            if case .networkError = apiError {
                // Network down — queue the workout for later and let the user move on.
                pendingStore.enqueue(workout)
                refreshPendingCount()
                queuedForLater = true
                resetWorkout()
            } else {
                self.error = apiError.localizedDescription
            }
        } catch {
            self.error = error.localizedDescription
        }

        isSaving = false
    }

    /// Attempts to upload every queued workout. Called on app foreground,
    /// after a successful save, and from the manual "Retry" button.
    func retryPendingWorkouts(silent: Bool = false) async {
        guard pendingStore.count > 0 else {
            refreshPendingCount()
            return
        }
        if !silent { isRetryingPending = true }
        _ = await pendingStore.drain()
        refreshPendingCount()
        if !silent {
            isRetryingPending = false
            if let drainError = pendingStore.lastDrainError {
                self.error = drainError
            }
        }
    }

    /// Sync local `@Published` mirror so views can show the badge without
    /// needing a direct `@ObservedObject` on the store.
    func refreshPendingCount() {
        pendingCount = pendingStore.count
        pendingStaleWarning = pendingStore.hasStaleWarning
    }

    func dismissXPReward() {
        xpRewardResponse = nil
        resetWorkout()
    }

    func resetWorkout() {
        selectedExercises = []
        workoutDate = Date()
        workoutNotes = ""
        sessionRPE = nil
    }
}

// MARK: - Local Models

struct LoggedExercise: Identifiable {
    let id = UUID()
    let exerciseId: String
    let exerciseName: String
    var sets: [LoggedSet]
    var supersetGroupId: UUID? = nil
}

struct LoggedSet: Identifiable {
    let id = UUID()
    var setNumber: Int
    var weightText: String = ""   // String binding for TextField (allows empty)
    var repsText: String = ""     // String binding for TextField (allows empty)
    var rpe: Int?
    var isBodyweight: Bool = false  // Toggle for bodyweight exercises (no added weight)

    // Computed properties for API/calculations
    var weight: Double { isBodyweight ? 0 : (Double(weightText) ?? 0) }
    var reps: Int { Int(repsText) ?? 0 }

    /// Creates a copy with incremented set number, preserving all input values
    func copyForNextSet() -> LoggedSet {
        LoggedSet(
            setNumber: setNumber + 1,
            weightText: weightText,
            repsText: repsText,
            rpe: rpe,
            isBodyweight: isBodyweight
        )
    }
}

/// Represents an item in the exercise list - either a single exercise or a superset group
enum ExerciseDisplayItem: Identifiable {
    case single(exercise: LoggedExercise, index: Int)
    case superset(groupId: UUID, exercises: [LoggedExercise], indices: [Int])

    var id: String {
        switch self {
        case .single(let exercise, _):
            return exercise.id.uuidString
        case .superset(let groupId, _, _):
            return groupId.uuidString
        }
    }
}
