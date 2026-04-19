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
    @Published var needsPaywall = false  // Set when 402 received

    // Inline-editable working copy of the extracted exercises. This is what gets
    // converted to LoggedExercises on save — NOT the original extraction, so the
    // user never has to burn another scan credit to fix a single mis-read set.
    @Published var editableExercises: [EditableExtractedExercise] = []

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
                    hydrateEditableExercises(from: data.exercises)
                }
            } catch APIError.paymentRequired(_) {
                self.needsPaywall = true
                self.error = "Insufficient scan credits. Purchase a scan pack to continue."
            } catch APIError.rateLimited(let message) {
                self.error = message
            } catch APIError.serviceUnavailable(let message) {
                self.error = message
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
                    hydrateEditableExercises(from: batch.exercises)
                }

                processingProgress = "Complete! Processed \(batchData?.screenshotsProcessed ?? 0) screenshots."
            } catch APIError.paymentRequired(_) {
                self.needsPaywall = true
                self.error = "Insufficient scan credits. Purchase a scan pack to continue."
            } catch APIError.rateLimited(let message) {
                self.error = message
            } catch APIError.serviceUnavailable(let message) {
                self.error = message
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
        // WHOOP activities don't have exercises to log
        if processedData?.isWhoopActivity == true || batchData?.isWhoopActivity == true {
            return []
        }

        // ALWAYS go through the editable copy so user edits are what gets saved.
        // If editableExercises is empty (shouldn't happen post-hydrate) fall back
        // to the raw extraction to preserve legacy behavior.
        if editableExercises.isEmpty {
            hydrateEditableExercises(from: processedData?.exercises ?? batchData?.exercises ?? [])
        }

        return editableExercises.compactMap { edited -> LoggedExercise? in
            guard let exerciseId = edited.matchedExerciseId else { return nil }
            let exerciseName = edited.displayName

            var setNumber = 1
            var loggedSets: [LoggedSet] = []

            for set in edited.sets {
                if set.isWarmup { continue }
                // Expand grouped sets (e.g. "3x10") into individual entries.
                let count = max(1, set.setsCount)
                for _ in 0..<count {
                    loggedSets.append(LoggedSet(
                        setNumber: setNumber,
                        weightText: set.weightText,
                        repsText: set.repsText,
                        rpe: nil
                    ))
                    setNumber += 1
                }
            }

            guard !loggedSets.isEmpty else { return nil }

            return LoggedExercise(
                exerciseId: exerciseId,
                exerciseName: exerciseName,
                sets: loggedSets
            )
        }
    }

    /// Seed the editable working copy from a freshly-extracted list. Called once
    /// per extraction; subsequent user edits live in `editableExercises` only.
    func hydrateEditableExercises(from extracted: [ExtractedExercise]) {
        editableExercises = extracted.map { EditableExtractedExercise(from: $0) }
    }

    /// Index of an editable exercise by its stable `UUID` — for sheet re-entry.
    func editableIndex(for id: UUID) -> Int? {
        editableExercises.firstIndex { $0.id == id }
    }

    /// Remove an edited exercise. The user can re-add via re-scanning if needed.
    func removeEditableExercise(id: UUID) {
        editableExercises.removeAll { $0.id == id }
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
        needsPaywall = false
        editableExercises = []
    }

    var formattedSelectedDate: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter.string(from: selectedDate)
    }

    var hasMatchedExercises: Bool {
        // WHOOP activities are saved by the backend directly — always allow.
        if processedData?.isWhoopActivity == true || batchData?.isWhoopActivity == true {
            return true
        }
        // Prefer the editable working copy (reflects user edits).
        if !editableExercises.isEmpty {
            return editableExercises.contains { $0.isMatched }
        }
        // Fall back to raw extraction if editables not yet hydrated.
        if let data = processedData {
            return data.exercises.contains { $0.matchedExerciseId != nil }
        }
        if let batch = batchData {
            return batch.exercises.contains { $0.matchedExerciseId != nil }
        }
        return false
    }

    var unmatchedExerciseCount: Int {
        if !editableExercises.isEmpty {
            return editableExercises.filter { !$0.isMatched }.count
        }
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
