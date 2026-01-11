import Foundation
import SwiftUI

// The Big Three - all known variations for each lift (first name is display name)
let bigThreeVariations: [[String]] = [
    ["Back Squat", "Barbell Back Squat", "Squat", "BB Squat", "Barbell Squat"],
    ["Bench Press", "Barbell Bench Press", "BB Bench", "Flat Bench Press", "Flat Barbell Bench Press"],
    ["Deadlift", "Barbell Deadlift", "Conventional Deadlift", "BB Deadlift"]
]

@MainActor
class ProgressViewModel: ObservableObject {
    @Published var exercises: [ExerciseResponse] = []
    @Published var selectedExercise: ExerciseResponse?
    @Published var trend: TrendResponse?
    @Published var percentiles: PercentilesResponse?
    @Published var prs: [PRResponse] = []
    @Published var bodyweightHistory: BodyweightHistoryResponse?
    @Published var selectedTimeRange = "12w"
    @Published var isLoading = false
    @Published var error: String?

    // Big Three tracking
    @Published var bigThreeTrends: [String: TrendResponse] = [:] // exerciseId -> trend
    @Published var additionalExerciseIds: [String] = [] // User-added exercises beyond Big Three
    @Published var additionalTrends: [String: TrendResponse] = [:] // exerciseId -> trend

    let timeRanges = ["4w", "8w", "12w", "26w", "52w"]

    var timeRangeLabel: String {
        switch selectedTimeRange {
        case "4w": return "4 Weeks"
        case "8w": return "8 Weeks"
        case "12w": return "12 Weeks"
        case "26w": return "6 Months"
        case "52w": return "1 Year"
        default: return selectedTimeRange
        }
    }

    // Get Big Three exercises from loaded exercises (matches any known variation)
    var bigThreeExercises: [ExerciseResponse] {
        bigThreeVariations.compactMap { variations in
            // Find the first exercise that matches any of the variations
            for variation in variations {
                if let exercise = exercises.first(where: { $0.name.caseInsensitiveCompare(variation) == .orderedSame }) {
                    return exercise
                }
            }
            return nil
        }
    }

    // Get additional tracked exercises
    var additionalExercises: [ExerciseResponse] {
        additionalExerciseIds.compactMap { id in
            exercises.first { $0.id == id }
        }
    }

    // Exercises available to add (not already tracked)
    var availableExercises: [ExerciseResponse] {
        let bigThreeIds = Set(bigThreeExercises.map { $0.id })
        let additionalIds = Set(additionalExerciseIds)
        return exercises.filter { !bigThreeIds.contains($0.id) && !additionalIds.contains($0.id) }
    }

    func loadInitialData() async {
        isLoading = true
        error = nil

        do {
            print("DEBUG: Loading exercises...")
            let exercisesResult = try await APIClient.shared.getExercises()
            print("DEBUG: Got \(exercisesResult.count) exercises")

            print("DEBUG: Loading percentiles...")
            let percentilesResult = try await APIClient.shared.getPercentiles()
            print("DEBUG: Got \(percentilesResult.exercises.count) exercises with percentiles")

            print("DEBUG: Loading PRs...")
            let prsResult = try await APIClient.shared.getPRs()
            print("DEBUG: Got \(prsResult.prs.count) PRs")

            print("DEBUG: Loading bodyweight...")
            let bodyweightResult = try await APIClient.shared.getBodyweightHistory()
            print("DEBUG: Got \(bodyweightResult.entries.count) bodyweight entries")

            exercises = exercisesResult
            percentiles = percentilesResult
            prs = prsResult.prs
            bodyweightHistory = bodyweightResult

            // Load trends for Big Three
            await loadBigThreeTrends()

            // Load trends for additional exercises
            await loadAdditionalTrends()

            // Set default selected exercise for detailed view
            if let first = bigThreeExercises.first {
                selectedExercise = first
                await loadTrend()
            }
        } catch let apiError as APIError {
            print("DEBUG: loadInitialData API error - \(apiError)")
            // Don't set error for unauthorized - user will be redirected to login
            if case .unauthorized = apiError {
                return
            }
            self.error = apiError.localizedDescription
        } catch {
            print("DEBUG: loadInitialData error - \(error)")
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadBigThreeTrends() async {
        for exercise in bigThreeExercises {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exercise.id,
                    timeRange: selectedTimeRange
                )
                bigThreeTrends[exercise.id] = trend
                print("DEBUG: Loaded trend for \(exercise.name)")
            } catch {
                print("DEBUG: Failed to load trend for \(exercise.name): \(error)")
            }
        }
    }

    func loadAdditionalTrends() async {
        for exerciseId in additionalExerciseIds {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exerciseId,
                    timeRange: selectedTimeRange
                )
                additionalTrends[exerciseId] = trend
            } catch {
                print("DEBUG: Failed to load trend for additional exercise: \(error)")
            }
        }
    }

    func loadTrend() async {
        guard let exerciseId = selectedExercise?.id else {
            print("DEBUG: No exercise selected")
            return
        }

        print("DEBUG: Loading trend for exercise \(exerciseId) with range \(selectedTimeRange)")

        do {
            trend = try await APIClient.shared.getExerciseTrend(
                exerciseId: exerciseId,
                timeRange: selectedTimeRange
            )
            print("DEBUG: Got trend with \(trend?.dataPoints.count ?? 0) data points")
        } catch {
            print("DEBUG: Trend error - \(error)")
            self.error = "Failed to load trend: \(error.localizedDescription)"
            trend = nil
        }
    }

    func selectExercise(_ exercise: ExerciseResponse) {
        selectedExercise = exercise
        Task {
            await loadTrend()
        }
    }

    func selectTimeRange(_ range: String) {
        selectedTimeRange = range
        Task {
            await loadBigThreeTrends()
            await loadAdditionalTrends()
            await loadTrend()
        }
    }

    func addExercise(_ exercise: ExerciseResponse) {
        guard !additionalExerciseIds.contains(exercise.id) else { return }
        additionalExerciseIds.append(exercise.id)
        Task {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exercise.id,
                    timeRange: selectedTimeRange
                )
                additionalTrends[exercise.id] = trend
            } catch {
                print("DEBUG: Failed to load trend for added exercise: \(error)")
            }
        }
    }

    func removeExercise(_ exerciseId: String) {
        additionalExerciseIds.removeAll { $0 == exerciseId }
        additionalTrends.removeValue(forKey: exerciseId)
    }

    func percentile(for exerciseId: String) -> ExercisePercentile? {
        percentiles?.exercises.first { $0.exerciseId == exerciseId }
    }

    func trend(for exerciseId: String) -> TrendResponse? {
        bigThreeTrends[exerciseId] ?? additionalTrends[exerciseId]
    }
}
