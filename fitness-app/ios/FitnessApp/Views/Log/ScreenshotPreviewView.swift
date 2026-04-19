import SwiftUI

struct ScreenshotPreviewView: View {
    @ObservedObject var viewModel: ScreenshotProcessingViewModel
    @Binding var isPresented: Bool
    let onConfirm: ([LoggedExercise]) -> Void

    @State private var hasStartedProcessing = false
    @State private var showDatePicker = false

    // Inline-edit state
    @State private var editingExerciseId: UUID?
    @State private var exerciseCatalog: [ExerciseResponse] = []

    private var buttonText: String {
        if viewModel.workoutSaved || viewModel.activitySaved {
            return "DONE"
        } else if viewModel.isWhoopActivity {
            return "ACTIVITY LOGGED"
        } else {
            return "USE THIS DATA"
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.05)

                if !hasStartedProcessing {
                    dateSelectionView
                } else if viewModel.isProcessing {
                    processingView
                } else if viewModel.error != nil {
                    errorView
                } else if let data = viewModel.processedData {
                    resultView(data: data)
                } else if let batch = viewModel.batchData {
                    batchResultView(batch: batch)
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
            .task {
                // Lazy-load exercise catalog so the match picker is ready when the user opens edit.
                if exerciseCatalog.isEmpty {
                    if let fetched = try? await APIClient.shared.getExercises() {
                        exerciseCatalog = fetched
                    }
                }
            }
            // fullScreenCover is over-kill for edit — a sheet is fine, and we use
            // `item:` binding so `.id()` isolation per exercise is automatic.
            .sheet(item: editingExerciseBinding) { editing in
                // Safety: re-resolve index on every open in case list mutated.
                if let idx = viewModel.editableIndex(for: editing.id) {
                    ScreenshotExerciseEditView(
                        exercises: exerciseCatalog,
                        exercise: $viewModel.editableExercises[idx],
                        onDeleteExercise: {
                            viewModel.removeEditableExercise(id: editing.id)
                            editingExerciseId = nil
                        }
                    )
                } else {
                    // Entry disappeared (e.g. deleted elsewhere) — close the sheet.
                    Color.clear.onAppear { editingExerciseId = nil }
                }
            }
        }
    }

    /// Bridge `editingExerciseId: UUID?` ↔ `Identifiable` for the sheet-item binding.
    private var editingExerciseBinding: Binding<EditingExerciseHandle?> {
        Binding(
            get: { editingExerciseId.map(EditingExerciseHandle.init) },
            set: { editingExerciseId = $0?.id }
        )
    }

    // MARK: - Date Selection View (shown before processing)

    private var dateSelectionView: some View {
        VStack(spacing: 24) {
            Spacer()

            // Header
            VStack(spacing: 12) {
                Text("[ SET QUEST DATE ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(2)

                ZStack {
                    Circle()
                        .fill(Color.systemPrimary.opacity(0.05))
                        .frame(width: 80, height: 80)

                    Image(systemName: "calendar.badge.clock")
                        .font(.system(size: 32))
                        .foregroundColor(.systemPrimary)
                }

                Text("When did this workout happen?")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text("\(viewModel.imageCount) screenshot\(viewModel.imageCount > 1 ? "s" : "") selected")
                    .font(.ariseBody(size: 14))
                    .foregroundColor(.textSecondary)
            }

            // Date Picker Button
            VStack(spacing: 12) {
                Button {
                    showDatePicker.toggle()
                } label: {
                    HStack {
                        Image(systemName: "calendar")
                            .foregroundColor(.systemPrimary)

                        Text(viewModel.formattedSelectedDate)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        Spacer()

                        Image(systemName: showDatePicker ? "chevron.up" : "chevron.down")
                            .foregroundColor(.textMuted)
                    }
                    .padding()
                    .background(Color.voidMedium)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                    )
                }
                .padding(.horizontal, 24)

                if showDatePicker {
                    DatePicker(
                        "Quest Date",
                        selection: $viewModel.selectedDate,
                        displayedComponents: .date
                    )
                    .datePickerStyle(.graphical)
                    .tint(.systemPrimary)
                    .padding(.horizontal, 24)
                    .background(Color.voidMedium)
                    .cornerRadius(8)
                    .padding(.horizontal, 24)
                }
            }

            Spacer()

            // Process Button
            Button {
                hasStartedProcessing = true
                Task {
                    await viewModel.processScreenshot()
                }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "wand.and.rays")
                        .font(.system(size: 16))
                    Text("ANALYZE SCREENSHOTS")
                        .font(.ariseHeader(size: 14, weight: .semibold))
                        .tracking(2)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 52)
                .background(Color.systemPrimary)
                .foregroundColor(.voidBlack)
                .cornerRadius(4)
                .shadow(color: .systemPrimaryGlow, radius: 15, x: 0, y: 0)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
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

                    if data.summary != nil {
                        Label("\(data.exercises.count) exercises", systemImage: "dumbbell")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding()
            .background(Color.voidMedium)

            // Exercises list — driven off the EDITABLE copy so user changes show here.
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(viewModel.editableExercises) { exercise in
                        EditableExercisePreviewCard(exercise: exercise) {
                            editingExerciseId = exercise.id
                        }
                    }

                    // Unmatched warning
                    if viewModel.unmatchedExerciseCount > 0 {
                        HStack(spacing: 12) {
                            Image(systemName: "exclamationmark.circle")
                                .foregroundColor(.yellow)

                            Text("\(viewModel.unmatchedExerciseCount) exercise(s) could not be matched and will be skipped. Tap to re-match.")
                                .font(.ariseBody(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                        .padding()
                        .background(Color.yellow.opacity(0.1))
                        .cornerRadius(8)
                    }

                    // Tap-to-edit hint
                    HStack(spacing: 8) {
                        Image(systemName: "hand.tap")
                            .font(.system(size: 11))
                            .foregroundColor(.textMuted)
                        Text("Tap any exercise to edit sets, reps, or the matched exercise.")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 4)
                }
                .padding()
            }

            // Action buttons
            VStack(spacing: 12) {
                // Workout/Activity saved confirmation
                if viewModel.workoutSaved || viewModel.activitySaved {
                    HStack(spacing: 12) {
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.green)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(viewModel.activitySaved ? "Activity Logged Successfully" : "Workout Logged Successfully")
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Text(viewModel.activitySaved ? "Your activity has been recorded" : "Your quest log has been recorded")
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
                    if viewModel.workoutSaved || viewModel.activitySaved || viewModel.isWhoopActivity {
                        // Just close if already saved or WHOOP activity (auto-saved by backend)
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
                        Image(systemName: (viewModel.workoutSaved || viewModel.activitySaved) ? "checkmark" : "checkmark.circle.fill")
                            .font(.system(size: 16))
                        Text(buttonText)
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .tracking(2)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background((viewModel.workoutSaved || viewModel.activitySaved) ? Color.green : (viewModel.hasMatchedExercises || viewModel.isWhoopActivity ? Color.systemPrimary : Color.gray))
                    .foregroundColor(.voidBlack)
                    .cornerRadius(4)
                    .shadow(color: (viewModel.workoutSaved || viewModel.activitySaved) ? Color.green.opacity(0.3) : .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                }
                .disabled(!viewModel.workoutSaved && !viewModel.activitySaved && !viewModel.hasMatchedExercises && !viewModel.isWhoopActivity)
            }
            .padding()
            .background(Color.voidMedium)
        }
    }

    // MARK: - Batch Result View

    private func batchResultView(batch: ScreenshotBatchResponse) -> some View {
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
                HStack(spacing: 8) {
                    Image(systemName: "photo.stack")
                        .foregroundColor(.systemPrimary)
                    Text("\(batch.screenshotsProcessed) screenshots combined")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textSecondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if let sessionName = batch.sessionName ?? batch.activityType {
                    Text(sessionName.uppercased())
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                HStack(spacing: 16) {
                    if let date = batch.sessionDate {
                        Label(date, systemImage: "calendar")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }

                    if let duration = batch.durationMinutes {
                        Label("\(duration) min", systemImage: "clock")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }

                    // Show activity type for WHOOP, exercises count for gym workouts
                    if batch.isWhoopActivity {
                        if let activityType = batch.activityType {
                            Label(activityType, systemImage: "figure.run")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                        if let strain = batch.strain {
                            Label(String(format: "%.1f strain", strain), systemImage: "flame")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textSecondary)
                        }
                    } else {
                        Label("\(batch.exercises.count) exercises", systemImage: "dumbbell")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding()
            .background(Color.voidMedium)

            // Content area - exercises or WHOOP activity details
            ScrollView {
                VStack(spacing: 12) {
                    if batch.isWhoopActivity {
                        // WHOOP Activity Card
                        VStack(alignment: .leading, spacing: 16) {
                            HStack {
                                Image(systemName: "figure.run")
                                    .font(.system(size: 24))
                                    .foregroundColor(.systemPrimary)
                                Text(batch.activityType?.uppercased() ?? "ACTIVITY")
                                    .font(.ariseHeader(size: 18, weight: .bold))
                                    .foregroundColor(.textPrimary)
                                Spacer()
                            }

                            // Metrics grid
                            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                                if let strain = batch.strain {
                                    MetricCard(icon: "flame", label: "STRAIN", value: String(format: "%.1f", strain))
                                }
                                if let calories = batch.calories {
                                    MetricCard(icon: "flame.fill", label: "CALORIES", value: "\(calories)")
                                }
                                if let avgHr = batch.avgHr {
                                    MetricCard(icon: "heart", label: "AVG HR", value: "\(avgHr) bpm")
                                }
                                if let maxHr = batch.maxHr {
                                    MetricCard(icon: "heart.fill", label: "MAX HR", value: "\(maxHr) bpm")
                                }
                                if let steps = batch.steps {
                                    MetricCard(icon: "figure.walk", label: "STEPS", value: "\(steps)")
                                }
                            }

                            if let timeRange = batch.timeRange {
                                HStack {
                                    Image(systemName: "clock")
                                        .foregroundColor(.textMuted)
                                    Text(timeRange)
                                        .font(.ariseMono(size: 12))
                                        .foregroundColor(.textSecondary)
                                }
                            }
                        }
                        .padding()
                        .background(Color.voidLight)
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                        )
                    } else {
                        // Gym workout exercises — editable
                        ForEach(viewModel.editableExercises) { exercise in
                            EditableExercisePreviewCard(exercise: exercise) {
                                editingExerciseId = exercise.id
                            }
                        }

                        // Unmatched warning
                        if viewModel.unmatchedExerciseCount > 0 {
                            HStack(spacing: 12) {
                                Image(systemName: "exclamationmark.circle")
                                    .foregroundColor(.yellow)

                                Text("\(viewModel.unmatchedExerciseCount) exercise(s) could not be matched and will be skipped. Tap to re-match.")
                                    .font(.ariseBody(size: 12))
                                    .foregroundColor(.textSecondary)
                            }
                            .padding()
                            .background(Color.yellow.opacity(0.1))
                            .cornerRadius(8)
                        }

                        // Tap-to-edit hint
                        HStack(spacing: 8) {
                            Image(systemName: "hand.tap")
                                .font(.system(size: 11))
                                .foregroundColor(.textMuted)
                            Text("Tap any exercise to edit sets, reps, or the matched exercise.")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 4)
                    }
                }
                .padding()
            }

            // Action buttons
            VStack(spacing: 12) {
                // Workout/Activity saved confirmation
                if viewModel.workoutSaved || viewModel.activitySaved {
                    HStack(spacing: 12) {
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 20))
                            .foregroundColor(.green)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(viewModel.activitySaved ? "Activity Logged Successfully" : "Workout Logged Successfully")
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)
                            Text(viewModel.activitySaved ? "Your activity has been recorded" : "Your quest log has been recorded")
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
                    if viewModel.workoutSaved || viewModel.activitySaved || viewModel.isWhoopActivity {
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
                        Image(systemName: (viewModel.workoutSaved || viewModel.activitySaved) ? "checkmark" : "checkmark.circle.fill")
                            .font(.system(size: 16))
                        Text(buttonText)
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .tracking(2)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background((viewModel.workoutSaved || viewModel.activitySaved) ? Color.green : (viewModel.hasMatchedExercises || viewModel.isWhoopActivity ? Color.systemPrimary : Color.gray))
                    .foregroundColor(.voidBlack)
                    .cornerRadius(4)
                    .shadow(color: (viewModel.workoutSaved || viewModel.activitySaved) ? Color.green.opacity(0.3) : .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                }
                .disabled(!viewModel.workoutSaved && !viewModel.activitySaved && !viewModel.hasMatchedExercises && !viewModel.isWhoopActivity)
            }
            .padding()
            .background(Color.voidMedium)
        }
    }
}

// MARK: - Exercise Preview Card

/// Lightweight Identifiable handle for `sheet(item:)` binding off a UUID.
private struct EditingExerciseHandle: Identifiable { let id: UUID }

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

// MARK: - Editable Exercise Preview Card

/// Tap-to-edit version of `ExercisePreviewCard` backed by the view model's
/// working copy. The source of truth for save is `viewModel.editableExercises`.
struct EditableExercisePreviewCard: View {
    let exercise: EditableExtractedExercise
    let onTap: () -> Void

    private var totalReps: Int {
        exercise.sets.filter { !$0.isWarmup }
            .reduce(0) { $0 + ($1.reps * max(1, $1.setsCount)) }
    }

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text(exercise.displayName)
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            if !exercise.isMatched {
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

                    if totalReps > 0 {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("\(totalReps)")
                                .font(.ariseHeader(size: 18, weight: .bold))
                                .foregroundColor(.systemPrimary)
                            Text("REPS")
                                .font(.ariseMono(size: 8))
                                .foregroundColor(.textMuted)
                        }
                    }

                    Image(systemName: "pencil")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .padding(.leading, 8)
                }

                // Sets strip
                if exercise.sets.isEmpty {
                    Text("No sets — tap to add")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                                EditableSetBadge(set: set, index: index + 1)
                            }
                        }
                    }
                }
            }
            .padding()
            .background(Color.voidLight.opacity(exercise.isMatched ? 1 : 0.5))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(exercise.isMatched ? Color.ariseBorder : Color.red.opacity(0.3), lineWidth: 1)
            )
            .cornerRadius(8)
            .opacity(exercise.isMatched ? 1 : 0.85)
        }
        .buttonStyle(.plain)
    }
}

struct EditableSetBadge: View {
    let set: EditableExtractedSet
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

            Text(set.weightText.isEmpty ? "—" : set.weightText)
                .font(.ariseMono(size: 12, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("×\(set.reps)")
                .font(.ariseMono(size: 10))
                .foregroundColor(.textSecondary)

            if set.setsCount > 1 {
                Text("×\(set.setsCount)")
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

// MARK: - Metric Card (for WHOOP activities)

struct MetricCard: View {
    let icon: String
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 20))
                .foregroundColor(.systemPrimary)

            Text(value)
                .font(.ariseHeader(size: 16, weight: .bold))
                .foregroundColor(.textPrimary)

            Text(label)
                .font(.ariseMono(size: 9))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Color.voidMedium)
        .cornerRadius(8)
    }
}
