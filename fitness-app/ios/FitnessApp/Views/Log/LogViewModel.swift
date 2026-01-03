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
                set.weight > 0 && set.reps > 0
            }
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
        let newSet = LoggedSet(
            setNumber: lastSet.setNumber + 1,
            weight: lastSet.weight,
            reps: lastSet.reps,
            rpe: lastSet.rpe
        )
        selectedExercises[exerciseIndex].sets.append(newSet)
    }

    func saveWorkout() async {
        guard canSave else { return }

        isSaving = true
        error = nil

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]

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
                }
            )
        }

        let workout = WorkoutCreate(
            date: formatter.string(from: workoutDate),
            durationMinutes: nil,
            sessionRpe: sessionRPE,
            notes: workoutNotes.isEmpty ? nil : workoutNotes,
            exercises: workoutExercises
        )

        do {
            let response = try await APIClient.shared.createWorkoutWithXP(workout)
            xpRewardResponse = response
            workoutSaved = true
            // Don't reset yet - wait for XP popup dismissal
        } catch {
            self.error = error.localizedDescription
        }

        isSaving = false
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
}

struct LoggedSet: Identifiable {
    let id = UUID()
    var setNumber: Int
    var weight: Double = 0
    var reps: Int = 0
    var rpe: Int?
}
