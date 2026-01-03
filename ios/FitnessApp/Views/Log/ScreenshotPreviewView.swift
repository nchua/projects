import SwiftUI

struct ScreenshotPreviewView: View {
    @ObservedObject var viewModel: ScreenshotProcessingViewModel
    @Binding var isPresented: Bool
    let onConfirm: ([LoggedExercise]) -> Void

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.05)

                if viewModel.isProcessing {
                    processingView
                } else if viewModel.error != nil {
                    errorView
                } else if let data = viewModel.processedData {
                    resultView(data: data)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        isPresented = false
                        viewModel.reset()
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "xmark")
                                .font(.system(size: 14, weight: .semibold))
                            Text("CANCEL")
                                .font(.ariseMono(size: 12, weight: .medium))
                                .tracking(1)
                        }
                        .foregroundColor(.textMuted)
                    }
                }
            }
            .toolbarBackground(Color.voidBlack, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
        }
        .task {
            await viewModel.processScreenshot()
        }
    }

    // MARK: - Processing View

    private var processingView: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                Circle()
                    .stroke(Color.systemPrimary.opacity(0.1), lineWidth: 3)
                    .frame(width: 80, height: 80)

                Circle()
                    .trim(from: 0, to: 0.7)
                    .stroke(Color.systemPrimary, lineWidth: 3)
                    .frame(width: 80, height: 80)
                    .rotationEffect(.degrees(-90))
                    .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: UUID())

                Image(systemName: "wand.and.rays")
                    .font(.system(size: 28))
                    .foregroundColor(.systemPrimary)
            }

            VStack(spacing: 8) {
                Text("[ SYSTEM ANALYZING ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(2)

                Text(viewModel.imageCount > 1 ? "Processing \(viewModel.imageCount) Screenshots" : "Extracting Workout Data")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(viewModel.imageCount > 1 ? "Combining all exercises into one workout..." : "The System is reading your quest log...")
                    .font(.ariseBody(size: 14))
                    .foregroundColor(.textSecondary)
            }

            Spacer()
        }
    }

    // MARK: - Error View

    private var errorView: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.red.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 32))
                    .foregroundColor(.red)
            }

            VStack(spacing: 8) {
                Text("[ SYSTEM ERROR ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.red)
                    .tracking(2)

                Text("Analysis Failed")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(viewModel.error ?? "Unknown error")
                    .font(.ariseBody(size: 14))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            Button {
                Task {
                    await viewModel.processScreenshot()
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "arrow.clockwise")
                    Text("TRY AGAIN")
                        .font(.ariseHeader(size: 14, weight: .semibold))
                        .tracking(2)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background(Color.voidMedium)
                .foregroundColor(.textPrimary)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
            }
            .padding(.horizontal, 24)

            Spacer()
        }
    }

    // MARK: - Result View

    private func resultView(data: ScreenshotProcessResponse) -> some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 12) {
                HStack {
                    Text(viewModel.workoutSaved ? "[ WORKOUT SAVED ]" : "[ EXTRACTION COMPLETE ]")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(viewModel.workoutSaved ? .green : .systemPrimary)
                        .tracking(2)

                    Spacer()

                    // Confidence badge
                    Text(viewModel.confidenceText)
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(viewModel.confidenceColor)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(viewModel.confidenceColor.opacity(0.1))
                        .cornerRadius(4)
                }

                // Batch indicator
                if viewModel.isBatchMode, let batch = viewModel.batchData {
                    HStack(spacing: 8) {
                        Image(systemName: "photo.stack")
                            .foregroundColor(.systemPrimary)
                        Text("\(batch.screenshotsProcessed) screenshots combined")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textSecondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                if let sessionName = data.sessionName {
                    Text(sessionName.uppercased())
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                HStack(spacing: 16) {
                    if let date = data.sessionDate {
                        Label(date, systemImage: "calendar")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }

                    if let duration = data.durationMinutes {
                        Label("\(duration) min", systemImage: "clock")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }

                    if let summary = data.summary {
                        Label("\(data.exercises.count) exercises", systemImage: "dumbbell")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding()
            .background(Color.voidMedium)

            // Exercises list
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(data.exercises) { exercise in
                        ExercisePreviewCard(exercise: exercise)
                    }

                    // Unmatched warning
                    if viewModel.unmatchedExerciseCount > 0 {
                        HStack(spacing: 12) {
                            Image(systemName: "exclamationmark.circle")
                                .foregroundColor(.yellow)

                            Text("\(viewModel.unmatchedExerciseCount) exercise(s) could not be matched and will be skipped")
                                .font(.ariseBody(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                        .padding()
                        .background(Color.yellow.opacity(0.1))
                        .cornerRadius(8)
                    }
                }
                .padding()
            }

            // Action buttons
            VStack(spacing: 12) {
                // Workout saved confirmation
                if viewModel.workoutSaved {
                    HStack(spacing: 12) {
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.green)

                        VStack(alignment: .leading, spacing: 2) {
                            Text("Workout Logged Successfully")
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Text("Your quest log has been recorded")
                                .font(.ariseBody(size: 12))
                                .foregroundColor(.textSecondary)
                        }

                        Spacer()
                    }
                    .padding()
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.green.opacity(0.3), lineWidth: 1)
                    )
                }

                Button {
                    if viewModel.workoutSaved {
                        // Just close if already saved
                        isPresented = false
                        viewModel.reset()
                    } else {
                        let exercises = viewModel.convertToLoggedExercises()
                        onConfirm(exercises)
                        isPresented = false
                        viewModel.reset()
                    }
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: viewModel.workoutSaved ? "checkmark" : "checkmark.circle.fill")
                            .font(.system(size: 16))
                        Text(viewModel.workoutSaved ? "DONE" : "USE THIS DATA")
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .tracking(2)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(viewModel.workoutSaved ? Color.green : (viewModel.hasMatchedExercises ? Color.systemPrimary : Color.gray))
                    .foregroundColor(.voidBlack)
                    .cornerRadius(4)
                    .shadow(color: viewModel.workoutSaved ? Color.green.opacity(0.3) : .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                }
                .disabled(!viewModel.workoutSaved && !viewModel.hasMatchedExercises)
            }
            .padding()
            .background(Color.voidMedium)
        }
    }
}

// MARK: - Exercise Preview Card

struct ExercisePreviewCard: View {
    let exercise: ExtractedExercise

    private var isMatched: Bool {
        exercise.matchedExerciseId != nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text(exercise.matchedExerciseName ?? exercise.name)
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        if !isMatched {
                            Text("UNMATCHED")
                                .font(.ariseMono(size: 8, weight: .medium))
                                .foregroundColor(.red)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.red.opacity(0.2))
                                .cornerRadius(3)
                        }
                    }

                    if let equipment = exercise.equipment {
                        Text(equipment.capitalized)
                            .font(.ariseMono(size: 10))
                            .foregroundColor(.textMuted)
                    }
                }

                Spacer()

                if let totalReps = exercise.totalReps {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(totalReps)")
                            .font(.ariseHeader(size: 18, weight: .bold))
                            .foregroundColor(.systemPrimary)
                        Text("REPS")
                            .font(.ariseMono(size: 8))
                            .foregroundColor(.textMuted)
                    }
                }
            }

            // Sets
            HStack(spacing: 8) {
                ForEach(Array(exercise.sets.enumerated()), id: \.offset) { index, set in
                    SetPreviewBadge(set: set, index: index + 1)
                }
            }
        }
        .padding()
        .background(Color.voidLight.opacity(isMatched ? 1 : 0.5))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isMatched ? Color.ariseBorder : Color.red.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(8)
        .opacity(isMatched ? 1 : 0.6)
    }
}

// MARK: - Set Preview Badge

struct SetPreviewBadge: View {
    let set: ExtractedSet
    let index: Int

    var body: some View {
        VStack(spacing: 2) {
            if set.isWarmup {
                Text("W")
                    .font(.ariseMono(size: 8, weight: .bold))
                    .foregroundColor(.yellow)
            } else {
                Text("\(index)")
                    .font(.ariseMono(size: 8, weight: .medium))
                    .foregroundColor(.textMuted)
            }

            Text("\(Int(set.weightLb))")
                .font(.ariseMono(size: 12, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("×\(set.reps)")
                .font(.ariseMono(size: 10))
                .foregroundColor(.textSecondary)

            if set.sets > 1 {
                Text("×\(set.sets)")
                    .font(.ariseMono(size: 8))
                    .foregroundColor(.systemPrimary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(set.isWarmup ? Color.yellow.opacity(0.1) : Color.voidMedium)
        .cornerRadius(4)
    }
}
