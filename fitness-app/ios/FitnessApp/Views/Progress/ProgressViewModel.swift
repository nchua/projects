import Foundation
import SwiftUI

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
        BigThree.orderedVariations.compactMap { variations in
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
            #if DEBUG
            print("DEBUG: Loading exercises...")
            #endif
            let exercisesResult = try await APIClient.shared.getExercises()
            #if DEBUG
            print("DEBUG: Got \(exercisesResult.count) exercises")

            print("DEBUG: Loading percentiles...")
            #endif
            let percentilesResult = try await APIClient.shared.getPercentiles()
            #if DEBUG
            print("DEBUG: Got \(percentilesResult.exercises.count) exercises with percentiles")

            print("DEBUG: Loading PRs...")
            #endif
            let prsResult = try await APIClient.shared.getPRs()
            #if DEBUG
            print("DEBUG: Got \(prsResult.prs.count) PRs")

            print("DEBUG: Loading bodyweight...")
            #endif
            let bodyweightResult = try await APIClient.shared.getBodyweightHistory()
            #if DEBUG
            print("DEBUG: Got \(bodyweightResult.entries.count) bodyweight entries")
            #endif

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
            #if DEBUG
            print("DEBUG: loadInitialData API error - \(apiError)")
            #endif
            // Don't set error for unauthorized - user will be redirected to login
            if case .unauthorized = apiError {
                return
            }
            self.error = apiError.localizedDescription
        } catch {
            #if DEBUG
            print("DEBUG: loadInitialData error - \(error)")
            #endif
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadBigThreeTrends() async {
        for exercise in bigThreeExercises {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exercise.id,
                    timeRange: selectedTimeRange,
                    includeSets: true
                )
                bigThreeTrends[exercise.id] = trend
                #if DEBUG
                print("DEBUG: Loaded trend for \(exercise.name)")
                #endif
            } catch {
                #if DEBUG
                print("DEBUG: Failed to load trend for \(exercise.name): \(error)")
                #endif
            }
        }
    }

    func loadAdditionalTrends() async {
        for exerciseId in additionalExerciseIds {
            do {
                let trend = try await APIClient.shared.getExerciseTrend(
                    exerciseId: exerciseId,
                    timeRange: selectedTimeRange,
                    includeSets: true
                )
                additionalTrends[exerciseId] = trend
            } catch {
                #if DEBUG
                print("DEBUG: Failed to load trend for additional exercise: \(error)")
                #endif
            }
        }
    }

    func loadTrend() async {
        guard let exerciseId = selectedExercise?.id else {
            #if DEBUG
            print("DEBUG: No exercise selected")
            #endif
            return
        }

        #if DEBUG
        print("DEBUG: Loading trend for exercise \(exerciseId) with range \(selectedTimeRange)")
        #endif

        do {
            trend = try await APIClient.shared.getExerciseTrend(
                exerciseId: exerciseId,
                timeRange: selectedTimeRange,
                includeSets: true
            )
            #if DEBUG
            print("DEBUG: Got trend with \(trend?.dataPoints.count ?? 0) data points")
            #endif
        } catch {
            #if DEBUG
            print("DEBUG: Trend error - \(error)")
            #endif
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
                    timeRange: selectedTimeRange,
                    includeSets: true
                )
                additionalTrends[exercise.id] = trend
            } catch {
                #if DEBUG
                print("DEBUG: Failed to load trend for added exercise: \(error)")
                #endif
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
