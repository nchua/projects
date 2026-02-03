import SwiftUI

/// Multi-goal wizard for setting up 1-5 strength goals
/// Flow: Intro -> Add Goals -> Review -> Submit
struct MultiGoalSetupView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = MultiGoalSetupViewModel()
    @State private var showAddGoalSheet = false
    var onComplete: (() -> Void)? = nil  // Callback when goals are created

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bgVoid.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Progress indicator
                    ProgressStepsIndicator(
                        currentStep: viewModel.currentStep,
                        totalSteps: 3
                    )
                    .padding(.top, 20)
                    .padding(.horizontal, 20)

                    // Step Content
                    TabView(selection: $viewModel.currentStep) {
                        IntroStep(viewModel: viewModel)
                            .tag(1)

                        GoalListStep(
                            viewModel: viewModel,
                            showAddGoalSheet: $showAddGoalSheet
                        )
                        .tag(2)

                        ReviewStep(viewModel: viewModel) {
                            onComplete?()
                            dismiss()
                        }
                        .tag(3)
                    }
                    .tabViewStyle(.page(indexDisplayMode: .never))
                    .animation(.easeInOut, value: viewModel.currentStep)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        if viewModel.currentStep > 1 {
                            viewModel.currentStep -= 1
                        } else {
                            dismiss()
                        }
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }

                ToolbarItem(placement: .principal) {
                    Text("Set Your Goals")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            .sheet(isPresented: $showAddGoalSheet) {
                AddGoalSheetView(viewModel: viewModel)
            }
        }
        .task {
            await viewModel.loadExercises()
        }
    }
}

// MARK: - Step 1: Intro

private struct IntroStep: View {
    @ObservedObject var viewModel: MultiGoalSetupViewModel

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            // Icon
            ZStack {
                Circle()
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 120, height: 120)

                Image(systemName: "target")
                    .font(.system(size: 56))
                    .foregroundColor(.systemPrimary)
            }

            // Title & Description
            VStack(spacing: 12) {
                Text("Set Your Strength Goals")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)

                Text("Add up to 5 exercises you want to get stronger at. We'll create a personalized weekly training plan to help you hit your targets.")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)
            }
            .padding(.horizontal, 20)

            // Features
            VStack(alignment: .leading, spacing: 16) {
                FeatureRow(icon: "chart.line.uptrend.xyaxis", text: "Track progress on multiple lifts")
                FeatureRow(icon: "calendar.badge.clock", text: "Intelligent workout scheduling")
                FeatureRow(icon: "figure.strengthtraining.traditional", text: "Balanced training splits")
            }
            .padding(20)
            .background(Color.bgCard)
            .cornerRadius(16)
            .padding(.horizontal, 20)

            Spacer()

            // Get Started Button
            Button {
                viewModel.currentStep = 2
            } label: {
                Text("Get Started")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(Color.systemPrimary)
                    .cornerRadius(50)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
    }
}

private struct FeatureRow: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(.systemPrimary)
                .frame(width: 24)

            Text(text)
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)

            Spacer()
        }
    }
}

// MARK: - Step 2: Goal List

private struct GoalListStep: View {
    @ObservedObject var viewModel: MultiGoalSetupViewModel
    @Binding var showAddGoalSheet: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Your Goals")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("Add \(viewModel.pendingGoals.isEmpty ? "1-5" : "up to \(5 - viewModel.pendingGoals.count) more") exercises")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .padding(.horizontal, 20)

            // Goal List
            ScrollView {
                VStack(spacing: 12) {
                    // Existing goals
                    ForEach(Array(viewModel.pendingGoals.enumerated()), id: \.element.id) { index, goal in
                        PendingGoalRow(
                            goal: goal,
                            onRemove: {
                                viewModel.pendingGoals.remove(at: index)
                            }
                        )
                    }

                    // Add Goal Button (if under limit)
                    if viewModel.pendingGoals.count < 5 {
                        Button {
                            showAddGoalSheet = true
                        } label: {
                            HStack(spacing: 12) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.systemPrimary.opacity(0.5), style: StrokeStyle(lineWidth: 2, dash: [6]))
                                        .frame(width: 44, height: 44)

                                    Image(systemName: "plus")
                                        .font(.system(size: 20, weight: .semibold))
                                        .foregroundColor(.systemPrimary)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Add Goal")
                                        .font(.system(size: 16, weight: .semibold))
                                        .foregroundColor(.systemPrimary)

                                    Text("\(viewModel.pendingGoals.count)/5 goals added")
                                        .font(.system(size: 13))
                                        .foregroundColor(.textSecondary)
                                }

                                Spacer()
                            }
                            .padding(16)
                            .background(Color.bgCard)
                            .cornerRadius(14)
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                            )
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .padding(.horizontal, 20)
            }

            Spacer()

            // Continue Button
            Button {
                viewModel.currentStep = 3
            } label: {
                Text("Continue")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(
                        viewModel.pendingGoals.isEmpty
                            ? Color.white.opacity(0.1)
                            : Color.systemPrimary
                    )
                    .cornerRadius(50)
            }
            .disabled(viewModel.pendingGoals.isEmpty)
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
    }
}

private struct PendingGoalRow: View {
    let goal: PendingGoal
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 44, height: 44)

                Text("🏋️")
                    .font(.system(size: 20))
            }

            // Info
            VStack(alignment: .leading, spacing: 4) {
                Text(goal.exerciseName)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)

                HStack(spacing: 8) {
                    Text("\(Int(goal.targetWeight)) \(goal.weightUnit) x \(goal.targetReps)")
                        .font(.system(size: 13))
                        .foregroundColor(.systemPrimary)

                    Text("by \(goal.deadline.formatted(date: .abbreviated, time: .omitted))")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary)
                }
            }

            Spacer()

            // Remove Button
            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 22))
                    .foregroundColor(.textSecondary)
            }
        }
        .padding(16)
        .background(Color.bgCard)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.05), lineWidth: 1)
        )
    }
}

// MARK: - Step 3: Review

private struct ReviewStep: View {
    @ObservedObject var viewModel: MultiGoalSetupViewModel
    let onComplete: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Title
                VStack(alignment: .leading, spacing: 8) {
                    Text("Review Your Goals")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(.white)

                    Text("Ready to start your training journey?")
                        .font(.system(size: 15))
                        .foregroundColor(.textSecondary)
                }
                .padding(.horizontal, 20)

                // Goals Summary
                VStack(spacing: 12) {
                    ForEach(viewModel.pendingGoals) { goal in
                        ReviewGoalRow(goal: goal)
                    }
                }
                .padding(.horizontal, 20)

                // Training Info
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 12) {
                        Image(systemName: "info.circle.fill")
                            .foregroundColor(.systemPrimary)

                        Text("What happens next")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        InfoRow(number: "1", text: "We'll analyze your goals and create a smart training split")
                        InfoRow(number: "2", text: "A personalized weekly mission will be generated")
                        InfoRow(number: "3", text: "Log workouts to track progress towards all goals")
                    }
                }
                .padding(20)
                .background(Color.bgCard)
                .cornerRadius(16)
                .padding(.horizontal, 20)

                // Error Display
                if let error = viewModel.error {
                    HStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                        Text(error)
                            .font(.system(size: 14))
                            .foregroundColor(.red)
                        Spacer()
                    }
                    .padding(16)
                    .background(Color.red.opacity(0.1))
                    .cornerRadius(12)
                    .padding(.horizontal, 20)
                }

                Spacer().frame(height: 100)
            }
            .padding(.top, 24)
        }
        .overlay(alignment: .bottom) {
            // Create Goals Button
            Button {
                Task {
                    await viewModel.createGoals()
                    if viewModel.goalsCreated {
                        onComplete()
                    }
                }
            } label: {
                HStack {
                    if viewModel.isCreating {
                        ProgressView()
                            .tint(.black)
                    } else {
                        Text("Create \(viewModel.pendingGoals.count) Goal\(viewModel.pendingGoals.count == 1 ? "" : "s")")
                            .font(.system(size: 16, weight: .bold))
                    }
                }
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 18)
                .background(
                    LinearGradient(
                        colors: [Color.systemPrimary, Color(hex: "00FF88")],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .cornerRadius(50)
                .shadow(color: Color.systemPrimary.opacity(0.35), radius: 20, y: 4)
            }
            .disabled(viewModel.isCreating)
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
            .background(
                LinearGradient(
                    colors: [Color.bgVoid.opacity(0), Color.bgVoid],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 100)
                .allowsHitTesting(false)
            )
        }
    }
}

private struct ReviewGoalRow: View {
    let goal: PendingGoal

    var body: some View {
        HStack(spacing: 14) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 44, height: 44)

                Text("🎯")
                    .font(.system(size: 20))
            }

            // Info
            VStack(alignment: .leading, spacing: 4) {
                Text(goal.exerciseName)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)

                HStack(spacing: 8) {
                    Text("\(Int(goal.targetWeight)) \(goal.weightUnit)")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.systemPrimary)

                    if goal.targetReps > 1 {
                        Text("x \(goal.targetReps)")
                            .font(.system(size: 14))
                            .foregroundColor(.systemPrimary)
                    }
                }
            }

            Spacer()

            // Deadline
            VStack(alignment: .trailing, spacing: 2) {
                Text("Target")
                    .font(.system(size: 11))
                    .foregroundColor(.textSecondary)

                Text(goal.deadline.formatted(date: .abbreviated, time: .omitted))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white)
            }
        }
        .padding(16)
        .background(Color.bgCard)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.systemPrimary.opacity(0.2), lineWidth: 1)
        )
    }
}

private struct InfoRow: View {
    let number: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(number)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.black)
                .frame(width: 20, height: 20)
                .background(Color.systemPrimary)
                .clipShape(Circle())

            Text(text)
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Add Goal Sheet

private struct AddGoalSheetView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var viewModel: MultiGoalSetupViewModel
    @State private var currentSubStep = 1
    @State private var searchText = ""
    @State private var selectedExercise: ExerciseResponse?
    @State private var targetWeight: Double = 225
    @State private var targetReps: Int = 1
    @State private var weightUnit: String = "lb"
    @State private var deadline: Date = Calendar.current.date(byAdding: .month, value: 2, to: Date()) ?? Date()
    @State private var currentMax: Double?
    @State private var isLoadingHistory = false
    @FocusState private var isSearchFocused: Bool

    // Exact Big Three exercise names to show at top
    private let bigThreeExact = [
        "Barbell Back Squat",
        "Barbell Bench Press",
        "Barbell Deadlift"
    ]

    var filteredExercises: [ExerciseResponse] {
        // Filter out already-selected exercises
        let selectedIds = Set(viewModel.pendingGoals.map { $0.exerciseId })
        let available = viewModel.exercises.filter { !selectedIds.contains($0.id) }

        if !searchText.isEmpty {
            return available.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }

        // Put Big Three at top, then rest alphabetically
        var bigThree: [ExerciseResponse] = []
        var others: [ExerciseResponse] = []

        for exercise in available {
            if bigThreeExact.contains(where: { $0.caseInsensitiveCompare(exercise.name) == .orderedSame }) {
                bigThree.append(exercise)
            } else {
                others.append(exercise)
            }
        }

        bigThree.sort { ex1, ex2 in
            let idx1 = bigThreeExact.firstIndex { $0.caseInsensitiveCompare(ex1.name) == .orderedSame } ?? 999
            let idx2 = bigThreeExact.firstIndex { $0.caseInsensitiveCompare(ex2.name) == .orderedSame } ?? 999
            return idx1 < idx2
        }

        return bigThree + others.sorted { $0.name < $1.name }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bgVoid.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Progress indicator
                    ProgressStepsIndicator(
                        currentStep: currentSubStep,
                        totalSteps: 3
                    )
                    .padding(.top, 20)
                    .padding(.horizontal, 20)

                    // Content based on sub-step
                    if currentSubStep == 1 {
                        exerciseSelectionContent
                    } else if currentSubStep == 2 {
                        targetWeightContent
                    } else {
                        deadlineContent
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        if currentSubStep > 1 {
                            currentSubStep -= 1
                        } else {
                            dismiss()
                        }
                    } label: {
                        Image(systemName: currentSubStep > 1 ? "chevron.left" : "xmark")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }

                ToolbarItem(placement: .principal) {
                    Text("Add Goal")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
        }
        .presentationDetents([.large])
    }

    // MARK: - Sub-step 1: Exercise Selection

    private var exerciseSelectionContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Choose Exercise")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What lift do you want to improve?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .padding(.horizontal, 20)

            // Search
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.textSecondary)
                TextField("Search exercises...", text: $searchText)
                    .foregroundColor(.white)
                    .focused($isSearchFocused)
                    .submitLabel(.done)
                    .onSubmit { isSearchFocused = false }

                if isSearchFocused {
                    Button { isSearchFocused = false } label: {
                        Image(systemName: "keyboard.chevron.compact.down")
                            .foregroundColor(.textSecondary)
                    }
                }
            }
            .padding(16)
            .background(Color.bgInput)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.white.opacity(0.1), lineWidth: 2)
            )
            .padding(.horizontal, 20)

            // Exercise List
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(filteredExercises) { exercise in
                        ExerciseSelectionRow(
                            exercise: exercise,
                            isSelected: selectedExercise?.id == exercise.id
                        ) {
                            isSearchFocused = false
                            selectedExercise = exercise
                            // Fetch current max
                            Task {
                                await fetchCurrentMax(for: exercise.id)
                            }
                        }
                    }
                }
                .padding(.horizontal, 20)
            }

            // Continue Button
            Button {
                isSearchFocused = false
                currentSubStep = 2
            } label: {
                HStack(spacing: 8) {
                    if isLoadingHistory {
                        ProgressView()
                            .tint(.black)
                            .scaleEffect(0.8)
                    }
                    Text(isLoadingHistory ? "Loading..." : "Continue")
                        .font(.system(size: 16, weight: .semibold))
                }
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 18)
                .background(
                    selectedExercise != nil && !isLoadingHistory
                        ? Color.systemPrimary
                        : Color.white.opacity(0.1)
                )
                .cornerRadius(50)
            }
            .disabled(selectedExercise == nil || isLoadingHistory)
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
    }

    // MARK: - Sub-step 2: Target Weight

    private var targetWeightContent: some View {
        VStack(spacing: 20) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Set Your Target")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What do you want to hit on \(selectedExercise?.name ?? "this exercise")?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20)

            Spacer()

            // Weight x Reps Display
            VStack(spacing: 12) {
                HStack(alignment: .lastTextBaseline, spacing: 8) {
                    Text("\(Int(targetWeight))")
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text(weightUnit)
                        .font(.system(size: 20))
                        .foregroundColor(.textSecondary)

                    Text("x")
                        .font(.system(size: 24, weight: .medium))
                        .foregroundColor(.textSecondary)
                        .padding(.horizontal, 4)

                    Text("\(targetReps)")
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text(targetReps == 1 ? "rep" : "reps")
                        .font(.system(size: 20))
                        .foregroundColor(.textSecondary)
                }

                if let max = currentMax {
                    Text("Current e1RM: \(Int(max)) \(weightUnit)")
                        .font(.system(size: 14))
                        .foregroundColor(.textSecondary)
                }
            }

            // Weight Controls
            VStack(spacing: 6) {
                Text("Weight")
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)

                HStack(spacing: 12) {
                    WeightControlButton(text: "-10", isLarge: true) {
                        targetWeight = max(0, targetWeight - 10)
                    }
                    WeightControlButton(text: "-5", isLarge: false) {
                        targetWeight = max(0, targetWeight - 5)
                    }
                    WeightControlButton(text: "+5", isLarge: false) {
                        targetWeight += 5
                    }
                    WeightControlButton(text: "+10", isLarge: true) {
                        targetWeight += 10
                    }
                }
            }

            // Reps Controls
            VStack(spacing: 6) {
                Text("Reps")
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)

                HStack(spacing: 12) {
                    RepControlButton(text: "-5", isLarge: true) {
                        targetReps = max(1, targetReps - 5)
                    }
                    RepControlButton(text: "-1", isLarge: false) {
                        targetReps = max(1, targetReps - 1)
                    }
                    RepControlButton(text: "+1", isLarge: false) {
                        targetReps = min(20, targetReps + 1)
                    }
                    RepControlButton(text: "+5", isLarge: true) {
                        targetReps = min(20, targetReps + 5)
                    }
                }
            }

            // Unit Toggle
            HStack(spacing: 0) {
                UnitToggleOption(text: "lbs", isSelected: weightUnit == "lb") {
                    weightUnit = "lb"
                }
                UnitToggleOption(text: "kg", isSelected: weightUnit == "kg") {
                    weightUnit = "kg"
                }
            }
            .background(Color.bgInput)
            .cornerRadius(50)

            Spacer()

            // Continue Button
            Button {
                currentSubStep = 3
            } label: {
                Text("Continue")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(Color.systemPrimary)
                    .cornerRadius(50)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
    }

    // MARK: - Sub-step 3: Deadline

    private var deadlineContent: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Set Deadline")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("When do you want to hit this target?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .padding(.horizontal, 20)

            // Date Picker
            DatePicker(
                "Target Date",
                selection: $deadline,
                in: Date()...,
                displayedComponents: .date
            )
            .datePickerStyle(.graphical)
            .tint(.systemPrimary)
            .colorScheme(.dark)
            .padding(20)
            .background(Color.bgCard)
            .cornerRadius(16)
            .padding(.horizontal, 20)

            Spacer()

            // Add Goal Button
            Button {
                addGoal()
                dismiss()
            } label: {
                Text("Add Goal")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(Color.systemPrimary)
                    .cornerRadius(50)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
    }

    // MARK: - Helpers

    private func fetchCurrentMax(for exerciseId: String) async {
        isLoadingHistory = true
        do {
            let trend = try await APIClient.shared.getExerciseTrend(
                exerciseId: exerciseId,
                timeRange: "all"
            )
            if let e1rm = trend.currentE1rm, e1rm > 0 {
                currentMax = e1rm
                targetWeight = (e1rm * 1.1).rounded()
            }
        } catch {
            print("Failed to fetch exercise history: \(error)")
        }
        isLoadingHistory = false
    }

    private func addGoal() {
        guard let exercise = selectedExercise else { return }

        let pendingGoal = PendingGoal(
            exerciseId: exercise.id,
            exerciseName: exercise.name,
            targetWeight: targetWeight,
            targetReps: targetReps,
            weightUnit: weightUnit,
            deadline: deadline
        )

        viewModel.pendingGoals.append(pendingGoal)
    }
}

// MARK: - View Model

struct PendingGoal: Identifiable {
    let id = UUID()
    let exerciseId: String
    let exerciseName: String
    let targetWeight: Double
    let targetReps: Int
    let weightUnit: String
    let deadline: Date
}

@MainActor
class MultiGoalSetupViewModel: ObservableObject {
    @Published var currentStep = 1
    @Published var exercises: [ExerciseResponse] = []
    @Published var pendingGoals: [PendingGoal] = []
    @Published var isCreating = false
    @Published var goalsCreated = false
    @Published var error: String?

    func loadExercises() async {
        do {
            exercises = try await APIClient.shared.getExercises()
            exercises.sort { ($0.category ?? "") < ($1.category ?? "") }
        } catch {
            print("Failed to load exercises: \(error)")
        }
    }

    func createGoals() async {
        guard !pendingGoals.isEmpty else {
            error = "No goals to create"
            return
        }

        isCreating = true
        error = nil

        do {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"

            let goalCreates = pendingGoals.map { goal in
                GoalCreate(
                    exerciseId: goal.exerciseId,
                    targetWeight: goal.targetWeight,
                    targetReps: goal.targetReps,
                    weightUnit: goal.weightUnit,
                    deadline: dateFormatter.string(from: goal.deadline),
                    notes: nil
                )
            }

            let response = try await APIClient.shared.createGoalsBatch(goalCreates)
            print("Created \(response.createdCount) goals, now \(response.activeCount) active")
            goalsCreated = true
        } catch {
            print("Failed to create goals: \(error)")
            self.error = "Failed to create goals: \(error.localizedDescription)"
        }

        isCreating = false
    }
}

#Preview {
    MultiGoalSetupView()
}
