import Foundation
import SwiftUI

@MainActor
class ScreenshotProcessingViewModel: ObservableObject {
    @Published var isProcessing = false
    @Published var processedData: ScreenshotProcessResponse?
    @Published var batchData: ScreenshotBatchResponse?
    @Published var error: String?
    @Published var selectedImagesData: [Data] = []
    @Published var processingProgress: String = ""
    @Published var workoutSaved = false
    @Published var savedWorkoutId: String?
    @Published var activitySaved = false
    @Published var savedActivityId: String?
    @Published var selectedDate: Date = Date()  // User-selectable date for the workout

    var isBatchMode: Bool {
        selectedImagesData.count > 1
    }

    var imageCount: Int {
        selectedImagesData.count
    }

    func processScreenshots() async {
        guard !selectedImagesData.isEmpty else {
            error = "No images selected"
            return
        }

        isProcessing = true
        error = nil
        workoutSaved = false
        savedWorkoutId = nil
        activitySaved = false
        savedActivityId = nil

        if selectedImagesData.count == 1 {
            // Single image - use regular endpoint
            processingProgress = "Analyzing screenshot..."

            do {
                let filename = "workout_\(Int(Date().timeIntervalSince1970)).jpg"
                processedData = try await APIClient.shared.processScreenshot(
                    imageData: selectedImagesData[0],
                    filename: filename,
                    sessionDate: selectedDate
                )
                processingProgress = "Complete!"

                // Check if workout/activity was saved
                if let data = processedData {
                    workoutSaved = data.workoutSaved
                    savedWorkoutId = data.workoutId
                    activitySaved = data.activitySaved
                    savedActivityId = data.activityId
                }
            } catch {
                self.error = error.localizedDescription
            }
        } else {
            // Multiple images - use batch endpoint
            processingProgress = "Analyzing \(selectedImagesData.count) screenshots..."

            do {
                let images = selectedImagesData.enumerated().map { index, data in
                    (data: data, filename: "workout_\(Int(Date().timeIntervalSince1970))_\(index).jpg")
                }

                batchData = try await APIClient.shared.processScreenshotsBatch(
                    images: images,
                    saveWorkout: true,
                    sessionDate: selectedDate
                )

                // Convert batch response to standard response for UI compatibility
                // Note: batch data is kept separately and processedData mirrors it
                if let batch = batchData {
                    workoutSaved = batch.workoutSaved
                    savedWorkoutId = batch.workoutId
                    activitySaved = batch.activitySaved
                    savedActivityId = batch.activityId
                }

                processingProgress = "Complete! Processed \(batchData?.screenshotsProcessed ?? 0) screenshots."
            } catch {
                self.error = error.localizedDescription
            }
        }

        isProcessing = false
    }

    // Legacy support - process single screenshot
    func processScreenshot() async {
        await processScreenshots()
    }

    func convertToLoggedExercises() -> [LoggedExercise] {
        // Get exercises from either processedData or batchData
        let exercises: [ExtractedExercise]
        if let data = processedData {
            // WHOOP activities don't have exercises to log
            if data.isWhoopActivity {
                return []
            }
            exercises = data.exercises
        } else if let batch = batchData {
            // WHOOP activities don't have exercises to log
            if batch.isWhoopActivity {
                return []
            }
            exercises = batch.exercises
        } else {
            return []
        }

        return exercises.compactMap { extracted -> LoggedExercise? in
            // Only include exercises that were matched to the database
            guard let exerciseId = extracted.matchedExerciseId else {
                return nil
            }

            let exerciseName = extracted.matchedExerciseName ?? extracted.name

            // Convert extracted sets to logged sets
            var setNumber = 1
            var loggedSets: [LoggedSet] = []

            for extractedSet in extracted.sets {
                // Skip warmup sets
                if extractedSet.isWarmup {
                    continue
                }

                // If the set has a count > 1, expand it
                let count = max(1, extractedSet.sets)
                for _ in 0..<count {
                    loggedSets.append(LoggedSet(
                        setNumber: setNumber,
                        weightText: String(extractedSet.weightLb),
                        repsText: String(extractedSet.reps),
                        rpe: nil
                    ))
                    setNumber += 1
                }
            }

            // Only include if we have working sets
            guard !loggedSets.isEmpty else { return nil }

            return LoggedExercise(
                exerciseId: exerciseId,
                exerciseName: exerciseName,
                sets: loggedSets
            )
        }
    }

    func reset() {
        isProcessing = false
        processedData = nil
        batchData = nil
        error = nil
        selectedImagesData = []
        processingProgress = ""
        workoutSaved = false
        savedWorkoutId = nil
        activitySaved = false
        savedActivityId = nil
        selectedDate = Date()
    }

    var formattedSelectedDate: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter.string(from: selectedDate)
    }

    var hasMatchedExercises: Bool {
        // Check processedData first, then batchData
        if let data = processedData {
            if data.isWhoopActivity {
                return true
            }
            return data.exercises.contains { $0.matchedExerciseId != nil }
        }
        if let batch = batchData {
            if batch.isWhoopActivity {
                return true
            }
            return batch.exercises.contains { $0.matchedExerciseId != nil }
        }
        return false
    }

    var unmatchedExerciseCount: Int {
        if let data = processedData {
            return data.exercises.filter { $0.matchedExerciseId == nil }.count
        }
        if let batch = batchData {
            return batch.exercises.filter { $0.matchedExerciseId == nil }.count
        }
        return 0
    }

    var confidenceColor: Color {
        let confidence = processedData?.processingConfidence ?? batchData?.processingConfidence
        guard let conf = confidence else { return .textMuted }
        switch conf {
        case "high":
            return .systemPrimary
        case "medium":
            return .yellow
        default:
            return .red
        }
    }

    var confidenceText: String {
        let confidence = processedData?.processingConfidence ?? batchData?.processingConfidence
        guard let conf = confidence else { return "" }
        switch conf {
        case "high":
            return "HIGH CONFIDENCE"
        case "medium":
            return "MEDIUM CONFIDENCE"
        default:
            return "LOW CONFIDENCE"
        }
    }

    // WHOOP/Activity detection
    var isWhoopActivity: Bool {
        processedData?.isWhoopActivity ?? batchData?.isWhoopActivity ?? false
    }

    var activityType: String? {
        processedData?.activityType ?? batchData?.activityType
    }

    var whoopStrain: Double? {
        processedData?.strain ?? batchData?.strain
    }

    var whoopCalories: Int? {
        processedData?.calories ?? batchData?.calories
    }

    var whoopSteps: Int? {
        processedData?.steps ?? batchData?.steps
    }

    var whoopAvgHR: Int? {
        processedData?.avgHr ?? batchData?.avgHr
    }

    var whoopTimeRange: String? {
        processedData?.timeRange ?? batchData?.timeRange
    }
}
