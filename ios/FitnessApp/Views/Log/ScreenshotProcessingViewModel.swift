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

        if selectedImagesData.count == 1 {
            // Single image - use regular endpoint
            processingProgress = "Analyzing screenshot..."

            do {
                let filename = "workout_\(Int(Date().timeIntervalSince1970)).jpg"
                processedData = try await APIClient.shared.processScreenshot(
                    imageData: selectedImagesData[0],
                    filename: filename
                )
                processingProgress = "Complete!"

                // Check if workout was saved
                if let data = processedData {
                    workoutSaved = data.workoutSaved
                    savedWorkoutId = data.workoutId
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
                    saveWorkout: true
                )

                // Convert batch response to standard response for UI compatibility
                if let batch = batchData {
                    processedData = ScreenshotProcessResponse(
                        sessionDate: batch.sessionDate,
                        sessionName: batch.sessionName,
                        durationMinutes: batch.durationMinutes,
                        summary: batch.summary,
                        exercises: batch.exercises,
                        processingConfidence: batch.processingConfidence,
                        workoutId: batch.workoutId,
                        workoutSaved: batch.workoutSaved
                    )
                    workoutSaved = batch.workoutSaved
                    savedWorkoutId = batch.workoutId
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
        guard let data = processedData else { return [] }

        return data.exercises.compactMap { extracted -> LoggedExercise? in
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
                        weight: extractedSet.weightLb,
                        reps: extractedSet.reps,
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
    }

    var hasMatchedExercises: Bool {
        guard let data = processedData else { return false }
        return data.exercises.contains { $0.matchedExerciseId != nil }
    }

    var unmatchedExerciseCount: Int {
        guard let data = processedData else { return 0 }
        return data.exercises.filter { $0.matchedExerciseId == nil }.count
    }

    var confidenceColor: Color {
        guard let data = processedData else { return .textMuted }
        switch data.processingConfidence {
        case "high":
            return .systemPrimary
        case "medium":
            return .yellow
        default:
            return .red
        }
    }

    var confidenceText: String {
        guard let data = processedData else { return "" }
        switch data.processingConfidence {
        case "high":
            return "HIGH CONFIDENCE"
        case "medium":
            return "MEDIUM CONFIDENCE"
        default:
            return "LOW CONFIDENCE"
        }
    }
}
