import SwiftUI

struct GoalSetupView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = GoalSetupViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bgVoid.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Progress Steps
                    ProgressStepsIndicator(currentStep: viewModel.currentStep, totalSteps: 5)
                        .padding(.top, 20)
                        .padding(.horizontal, 20)

                    // Step Content
                    TabView(selection: $viewModel.currentStep) {
                        Step1ExerciseSelection(viewModel: viewModel)
                            .tag(1)

                        Step2CurrentAbility(viewModel: viewModel)
                            .tag(2)

                        Step3TargetWeight(viewModel: viewModel)
                            .tag(3)

                        Step4Deadline(viewModel: viewModel)
                            .tag(4)

                        Step5Confirmation(viewModel: viewModel, onComplete: {
                            dismiss()
                        })
                            .tag(5)
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
                            // If on Step 3 and we skipped Step 2 (has history), go back to Step 1
                            if viewModel.currentStep == 3 && viewModel.hasExerciseHistory {
                                viewModel.currentStep = 1
                            } else {
                                viewModel.currentStep -= 1
                            }
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
                    Text("New Strength Goal")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
        }
        .task {
            await viewModel.loadExercises()
        }
    }
}

// MARK: - Progress Steps Indicator

struct ProgressStepsIndicator: View {
    let currentStep: Int
    let totalSteps: Int

    var body: some View {
        HStack(spacing: 8) {
            ForEach(1...totalSteps, id: \.self) { step in
                Capsule()
                    .fill(stepColor(for: step))
                    .frame(height: 4)
            }
        }
    }

    private func stepColor(for step: Int) -> Color {
        if step < currentStep {
            return Color(hex: "00FF88") // Completed
        } else if step == currentStep {
            return Color.systemPrimary // Active
        } else {
            return Color.white.opacity(0.1) // Future
        }
    }
}

// MARK: - Step 1: Exercise Selection

struct Step1ExerciseSelection: View {
    @ObservedObject var viewModel: GoalSetupViewModel
    @State private var searchText = ""
    @FocusState private var isSearchFocused: Bool

    // Exact Big Three exercise names to show at top (in order)
    private let bigThreeExact = [
        "Barbell Back Squat",
        "Barbell Bench Press",
        "Barbell Deadlift"
    ]

    var filteredExercises: [ExerciseResponse] {
        if !searchText.isEmpty {
            return viewModel.exercises.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }

        // Put exact Big Three at top, then rest alphabetically
        var bigThree: [ExerciseResponse] = []
        var others: [ExerciseResponse] = []

        for exercise in viewModel.exercises {
            if bigThreeExact.contains(where: { $0.caseInsensitiveCompare(exercise.name) == .orderedSame }) {
                bigThree.append(exercise)
            } else {
                others.append(exercise)
            }
        }

        // Sort Big Three by defined order
        bigThree.sort { ex1, ex2 in
            let idx1 = bigThreeExact.firstIndex { $0.caseInsensitiveCompare(ex1.name) == .orderedSame } ?? 999
            let idx2 = bigThreeExact.firstIndex { $0.caseInsensitiveCompare(ex2.name) == .orderedSame } ?? 999
            return idx1 < idx2
        }

        return bigThree + others.sorted { $0.name < $1.name }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Choose Your Lift")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What exercise do you want to get stronger at?")
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
                    .onSubmit {
                        isSearchFocused = false
                    }

                if isSearchFocused {
                    Button {
                        isSearchFocused = false
                    } label: {
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
                            isSelected: viewModel.selectedExercise?.id == exercise.id
                        ) {
                            isSearchFocused = false  // Dismiss keyboard
                            viewModel.selectedExercise = exercise
                            // Fetch current max from workout history
                            Task {
                                await viewModel.fetchCurrentMax(for: exercise.id)
                            }
                        }
                    }
                }
                .padding(.horizontal, 20)
            }

            // Show current max when exercise is selected and has history
            if viewModel.selectedExercise != nil && viewModel.hasExerciseHistory, let currentMax = viewModel.currentMax {
                HStack(spacing: 12) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 16))
                        .foregroundColor(.systemPrimary)

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Current max from history")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)

                        Text("\(Int(currentMax)) \(viewModel.weightUnit)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    Spacer()
                }
                .padding(14)
                .background(Color.systemPrimary.opacity(0.1))
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                )
                .padding(.horizontal, 20)
            }

            // Continue Button
            Button {
                isSearchFocused = false  // Dismiss keyboard
                if viewModel.hasExerciseHistory {
                    // Skip current ability step - we have history
                    viewModel.currentStep = 3
                } else {
                    // Show manual entry step
                    viewModel.currentStep = 2
                }
            } label: {
                HStack(spacing: 8) {
                    if viewModel.isLoadingHistory {
                        ProgressView()
                            .tint(.black)
                            .scaleEffect(0.8)
                    }
                    Text(viewModel.isLoadingHistory ? "Loading history..." : "Continue")
                        .font(.system(size: 16, weight: .semibold))
                }
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 18)
                .background(
                    viewModel.selectedExercise != nil && !viewModel.isLoadingHistory
                        ? Color.systemPrimary
                        : Color.white.opacity(0.1)
                )
                .cornerRadius(50)
            }
            .disabled(viewModel.selectedExercise == nil || viewModel.isLoadingHistory)
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
    }
}

struct ExerciseSelectionRow: View {
    let exercise: ExerciseResponse
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                // Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(Color.white.opacity(0.05))
                        .frame(width: 44, height: 44)

                    Text("🏋️")
                        .font(.system(size: 20))
                }

                // Info
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.name)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white)

                    Text(exercise.category ?? "Exercise")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary)
                }

                Spacer()

                // Check
                Circle()
                    .fill(isSelected ? Color.systemPrimary : Color.clear)
                    .frame(width: 24, height: 24)
                    .overlay(
                        Circle()
                            .stroke(isSelected ? Color.systemPrimary : Color.white.opacity(0.2), lineWidth: 2)
                    )
                    .overlay(
                        isSelected ?
                            Image(systemName: "checkmark")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.black)
                            : nil
                    )
            }
            .padding(16)
            .background(Color.bgCard)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(
                        isSelected ? Color.systemPrimary : Color.clear,
                        lineWidth: 2
                    )
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Step 2: Current Ability

struct Step2CurrentAbility: View {
    @ObservedObject var viewModel: GoalSetupViewModel
    @FocusState private var focusedField: Field?

    enum Field {
        case weight, reps
    }

    var body: some View {
        VStack(spacing: 24) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Your Current Ability")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What can you \(viewModel.selectedExercise?.name ?? "lift") today?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20)

            Spacer()

            // Weight Input
            VStack(spacing: 8) {
                Text("Weight")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)

                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    TextField("0", text: $viewModel.currentWeightInput)
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.white)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 150)
                        .focused($focusedField, equals: .weight)

                    Text(viewModel.weightUnit)
                        .font(.system(size: 24))
                        .foregroundColor(.textSecondary)
                }
            }

            // Reps Input
            VStack(spacing: 8) {
                Text("Reps")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)

                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    TextField("0", text: $viewModel.currentRepsInput)
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.white)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 100)
                        .focused($focusedField, equals: .reps)

                    Text("reps")
                        .font(.system(size: 24))
                        .foregroundColor(.textSecondary)
                }
            }

            // Estimated 1RM Display
            if viewModel.calculatedE1RM > 0 {
                VStack(spacing: 4) {
                    Text("Estimated 1RM")
                        .font(.system(size: 12))
                        .foregroundColor(.textSecondary)

                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                        Text("\(Int(viewModel.calculatedE1RM))")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.systemPrimary)

                        Text(viewModel.weightUnit)
                            .font(.system(size: 16))
                            .foregroundColor(.textSecondary)
                    }
                }
                .padding(16)
                .background(Color.systemPrimary.opacity(0.1))
                .cornerRadius(14)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                )
            }

            // Unit Toggle
            HStack(spacing: 0) {
                UnitToggleOption(text: "lbs", isSelected: viewModel.weightUnit == "lb") {
                    viewModel.weightUnit = "lb"
                }
                UnitToggleOption(text: "kg", isSelected: viewModel.weightUnit == "kg") {
                    viewModel.weightUnit = "kg"
                }
            }
            .background(Color.bgInput)
            .cornerRadius(50)

            Spacer()

            // Continue Button
            Button {
                focusedField = nil
                viewModel.updateCurrentMax()
                viewModel.currentStep = 3
            } label: {
                Text("Continue")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(
                        viewModel.hasValidCurrentAbility
                            ? Color.systemPrimary
                            : Color.white.opacity(0.1)
                    )
                    .cornerRadius(50)
            }
            .disabled(!viewModel.hasValidCurrentAbility)
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
        .padding(.top, 24)
        .onTapGesture {
            focusedField = nil
        }
    }
}

// MARK: - Step 3: Target Weight

struct Step3TargetWeight: View {
    @ObservedObject var viewModel: GoalSetupViewModel

    var body: some View {
        VStack(spacing: 20) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Set Your Target")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What weight and reps do you want to hit on \(viewModel.selectedExercise?.name ?? "this exercise")?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20)

            Spacer()

            // Weight x Reps Display
            VStack(spacing: 12) {
                HStack(alignment: .lastTextBaseline, spacing: 8) {
                    Text("\(Int(viewModel.targetWeight))")
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text(viewModel.weightUnit)
                        .font(.system(size: 20))
                        .foregroundColor(.textSecondary)

                    Text("x")
                        .font(.system(size: 24, weight: .medium))
                        .foregroundColor(.textSecondary)
                        .padding(.horizontal, 4)

                    Text("\(viewModel.targetReps)")
                        .font(.system(size: 56, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text(viewModel.targetReps == 1 ? "rep" : "reps")
                        .font(.system(size: 20))
                        .foregroundColor(.textSecondary)
                }

                if let currentMax = viewModel.currentMax {
                    VStack(spacing: 4) {
                        Text("Your current e1RM: \(Int(currentMax)) \(viewModel.weightUnit)")
                            .font(.system(size: 14))
                            .foregroundColor(.textSecondary)

                        if viewModel.hasExerciseHistory {
                            Text("(from workout history)")
                                .font(.system(size: 12))
                                .foregroundColor(.systemPrimary.opacity(0.7))
                        }
                    }
                }
            }

            // Weight Controls
            VStack(spacing: 6) {
                Text("Weight")
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)

                HStack(spacing: 12) {
                    WeightControlButton(text: "-10", isLarge: true) {
                        viewModel.targetWeight = max(0, viewModel.targetWeight - 10)
                    }
                    WeightControlButton(text: "-5", isLarge: false) {
                        viewModel.targetWeight = max(0, viewModel.targetWeight - 5)
                    }
                    WeightControlButton(text: "+5", isLarge: false) {
                        viewModel.targetWeight += 5
                    }
                    WeightControlButton(text: "+10", isLarge: true) {
                        viewModel.targetWeight += 10
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
                        viewModel.targetReps = max(1, viewModel.targetReps - 5)
                    }
                    RepControlButton(text: "-1", isLarge: false) {
                        viewModel.targetReps = max(1, viewModel.targetReps - 1)
                    }
                    RepControlButton(text: "+1", isLarge: false) {
                        viewModel.targetReps = min(20, viewModel.targetReps + 1)
                    }
                    RepControlButton(text: "+5", isLarge: true) {
                        viewModel.targetReps = min(20, viewModel.targetReps + 5)
                    }
                }
            }

            // Unit Toggle
            HStack(spacing: 0) {
                UnitToggleOption(text: "lbs", isSelected: viewModel.weightUnit == "lb") {
                    viewModel.weightUnit = "lb"
                }
                UnitToggleOption(text: "kg", isSelected: viewModel.weightUnit == "kg") {
                    viewModel.weightUnit = "kg"
                }
            }
            .background(Color.bgInput)
            .cornerRadius(50)

            Spacer()

            // Progress needed (comparing e1RMs)
            if let currentMax = viewModel.currentMax, viewModel.targetE1RM > currentMax {
                let diff = viewModel.targetE1RM - currentMax
                let percent = (diff / currentMax) * 100

                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Progress needed")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)

                        HStack(spacing: 8) {
                            Text("+\(Int(diff)) \(viewModel.weightUnit) e1RM (+\(String(format: "%.1f", percent))%)")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                        }

                        if viewModel.targetReps > 1 {
                            Text("Target e1RM: \(Int(viewModel.targetE1RM)) \(viewModel.weightUnit)")
                                .font(.system(size: 12))
                                .foregroundColor(.systemPrimary.opacity(0.8))
                        }
                    }
                    Spacer()
                }
                .padding(16)
                .background(Color.systemPrimary.opacity(0.1))
                .cornerRadius(14)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
                )
                .overlay(
                    Rectangle()
                        .fill(Color.systemPrimary)
                        .frame(width: 3)
                        .offset(x: -0.5),
                    alignment: .leading
                )
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .padding(.horizontal, 20)
            }

            // Continue Button
            Button {
                viewModel.currentStep = 4
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
}

struct WeightControlButton: View {
    let text: String
    let isLarge: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(text)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(isLarge ? Color.systemPrimary : .white)
                .frame(width: 56, height: 56)
                .background(isLarge ? Color.systemPrimary.opacity(0.2) : Color.bgInput)
                .clipShape(Circle())
        }
    }
}

struct RepControlButton: View {
    let text: String
    let isLarge: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(text)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(isLarge ? Color(hex: "00FF88") : .white)
                .frame(width: 56, height: 56)
                .background(isLarge ? Color(hex: "00FF88").opacity(0.2) : Color.bgInput)
                .clipShape(Circle())
        }
    }
}

struct UnitToggleOption: View {
    let text: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(text)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(isSelected ? .black : .textSecondary)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(isSelected ? Color.systemPrimary : Color.clear)
                .cornerRadius(50)
        }
    }
}

// MARK: - Step 4: Deadline

struct Step4Deadline: View {
    @ObservedObject var viewModel: GoalSetupViewModel

    var weeksRemaining: Int {
        let days = Calendar.current.dateComponents([.day], from: Date(), to: viewModel.deadline).day ?? 0
        return max(0, days / 7)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Set Your Deadline")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("When do you want to hit \(Int(viewModel.targetWeight)) \(viewModel.weightUnit) x \(viewModel.targetReps) on \(viewModel.selectedExercise?.name ?? "this exercise")?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .padding(.horizontal, 20)

            // Date Picker
            DatePicker(
                "Target Date",
                selection: $viewModel.deadline,
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

            // Deadline Summary
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Target Date")
                        .font(.system(size: 12))
                        .foregroundColor(.textSecondary)

                    Text(viewModel.deadline, style: .date)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(.white)

                    Text("\(weeksRemaining) weeks from now")
                        .font(.system(size: 14))
                        .foregroundColor(.systemPrimary)
                }
                Spacer()
            }
            .padding(16)
            .background(Color.systemPrimary.opacity(0.1))
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
            )
            .overlay(
                Rectangle()
                    .fill(Color.systemPrimary)
                    .frame(width: 3)
                    .offset(x: -0.5),
                alignment: .leading
            )
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .padding(.horizontal, 20)

            Spacer()

            // Continue Button
            Button {
                viewModel.currentStep = 5
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
}

// MARK: - Step 5: Confirmation

struct Step5Confirmation: View {
    @ObservedObject var viewModel: GoalSetupViewModel
    let onComplete: () -> Void

    var weeksRemaining: Int {
        let days = Calendar.current.dateComponents([.day], from: Date(), to: viewModel.deadline).day ?? 0
        return max(0, days / 7)
    }

    var progressNeeded: Double {
        guard let currentMax = viewModel.currentMax, currentMax > 0 else { return 0 }
        return viewModel.targetE1RM - currentMax
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Title
                VStack(alignment: .leading, spacing: 8) {
                    Text("Your Goal")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(.white)

                    Text("Ready to start your journey?")
                        .font(.system(size: 15))
                        .foregroundColor(.textSecondary)
                }
                .padding(.horizontal, 20)

                // Goal Summary Card
                VStack(spacing: 24) {
                    // Header
                    HStack(spacing: 16) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Color.systemPrimary.opacity(0.15))
                                .frame(width: 60, height: 60)

                            Text("🏋️")
                                .font(.system(size: 28))
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text(viewModel.selectedExercise?.name ?? "Exercise")
                                .font(.system(size: 20, weight: .bold))
                                .foregroundColor(.white)

                            HStack(alignment: .lastTextBaseline, spacing: 4) {
                                Text("\(Int(viewModel.targetWeight))")
                                    .font(.system(size: 32, weight: .bold))
                                    .foregroundColor(.systemPrimary)

                                Text(viewModel.weightUnit)
                                    .font(.system(size: 16))
                                    .foregroundColor(.textSecondary)

                                Text("x")
                                    .font(.system(size: 18, weight: .medium))
                                    .foregroundColor(.textSecondary)
                                    .padding(.horizontal, 2)

                                Text("\(viewModel.targetReps)")
                                    .font(.system(size: 32, weight: .bold))
                                    .foregroundColor(.systemPrimary)

                                Text(viewModel.targetReps == 1 ? "rep" : "reps")
                                    .font(.system(size: 16))
                                    .foregroundColor(.textSecondary)
                            }
                        }

                        Spacer()
                    }

                    // Details
                    VStack(spacing: 0) {
                        GoalDetailRow(label: "Current e1RM", value: viewModel.currentMax != nil ? "\(Int(viewModel.currentMax!)) \(viewModel.weightUnit)" : "Unknown")

                        Divider().background(Color.white.opacity(0.05))

                        if viewModel.targetReps > 1 {
                            GoalDetailRow(label: "Target e1RM", value: "\(Int(viewModel.targetE1RM)) \(viewModel.weightUnit)")

                            Divider().background(Color.white.opacity(0.05))
                        }

                        GoalDetailRow(label: "Progress Needed", value: "+\(Int(progressNeeded)) \(viewModel.weightUnit) e1RM", isHighlight: true)

                        Divider().background(Color.white.opacity(0.05))

                        GoalDetailRow(label: "Deadline", value: viewModel.deadline.formatted(date: .abbreviated, time: .omitted))

                        Divider().background(Color.white.opacity(0.05))

                        GoalDetailRow(label: "Time Remaining", value: "\(weeksRemaining) weeks")
                    }
                }
                .padding(24)
                .background(
                    LinearGradient(
                        colors: [Color.bgCard, Color.bgElevated],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .cornerRadius(20)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(Color.systemPrimary.opacity(0.2), lineWidth: 1)
                )
                .padding(.horizontal, 20)

                // Mission Preview
                VStack(alignment: .leading, spacing: 16) {
                    Text("Weekly training: ~3 workouts recommended")
                        .font(.system(size: 14))
                        .foregroundColor(.textSecondary)

                    HStack(spacing: 8) {
                        ForEach(["S", "M", "T", "W", "T", "F", "S"], id: \.self) { day in
                            let isWorkoutDay = ["M", "W", "F"].contains(day)
                            VStack(spacing: 4) {
                                Text(day)
                                    .font(.system(size: 10))
                                    .foregroundColor(.textSecondary)

                                Text(isWorkoutDay ? "💪" : "-")
                                    .font(.system(size: 16))
                                    .foregroundColor(isWorkoutDay ? .systemPrimary : .textSecondary)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(isWorkoutDay ? Color.systemPrimary.opacity(0.1) : Color.white.opacity(0.03))
                            .cornerRadius(10)
                            .overlay(
                                RoundedRectangle(cornerRadius: 10)
                                    .stroke(isWorkoutDay ? Color.systemPrimary.opacity(0.3) : Color.clear, lineWidth: 1)
                            )
                        }
                    }
                }
                .padding(20)
                .background(Color.bgCard)
                .cornerRadius(16)
                .padding(.horizontal, 20)

                Spacer().frame(height: 100)
            }
            .padding(.top, 24)
        }
        .overlay(alignment: .bottom) {
            // Create Goal Button
            Button {
                Task {
                    await viewModel.createGoal()
                    if viewModel.goalCreated {
                        onComplete()
                    }
                }
            } label: {
                HStack {
                    if viewModel.isCreating {
                        ProgressView()
                            .tint(.black)
                    } else {
                        Text("Create Goal")
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

struct GoalDetailRow: View {
    let label: String
    let value: String
    var isHighlight: Bool = false

    var body: some View {
        HStack {
            Text(label)
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)

            Spacer()

            Text(value)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(isHighlight ? Color(hex: "00FF88") : .white)
        }
        .padding(.vertical, 12)
    }
}

// MARK: - View Model

@MainActor
class GoalSetupViewModel: ObservableObject {
    @Published var currentStep = 1
    @Published var exercises: [ExerciseResponse] = []
    @Published var selectedExercise: ExerciseResponse?
    @Published var targetWeight: Double = 225
    @Published var targetReps: Int = 1  // Target rep count (1 = true 1RM)
    @Published var weightUnit: String = "lb"
    @Published var deadline: Date = Calendar.current.date(byAdding: .month, value: 2, to: Date()) ?? Date()
    @Published var currentMax: Double?
    @Published var isCreating = false
    @Published var goalCreated = false
    @Published var error: String?

    // History loading state
    @Published var isLoadingHistory = false
    @Published var hasExerciseHistory = false

    // Current ability inputs
    @Published var currentWeightInput: String = ""
    @Published var currentRepsInput: String = ""

    // Calculated e1RM using Epley formula: weight * (1 + reps/30)
    var calculatedE1RM: Double {
        guard let weight = Double(currentWeightInput),
              let reps = Int(currentRepsInput),
              weight > 0, reps > 0 else {
            return 0
        }
        // For 1 rep, e1RM = weight
        if reps == 1 {
            return weight
        }
        // Epley formula
        return weight * (1 + Double(reps) / 30)
    }

    // Target e1RM based on targetWeight and targetReps
    var targetE1RM: Double {
        if targetReps == 1 {
            return targetWeight
        }
        return targetWeight * (1 + Double(targetReps) / 30)
    }

    var hasValidCurrentAbility: Bool {
        guard let weight = Double(currentWeightInput),
              let reps = Int(currentRepsInput) else {
            return false
        }
        return weight > 0 && reps > 0
    }

    func updateCurrentMax() {
        if calculatedE1RM > 0 {
            currentMax = calculatedE1RM
        }
    }

    func fetchCurrentMax(for exerciseId: String) async {
        isLoadingHistory = true
        hasExerciseHistory = false

        do {
            let trend = try await APIClient.shared.getExerciseTrend(
                exerciseId: exerciseId,
                timeRange: "all"
            )
            if let e1rm = trend.currentE1rm, e1rm > 0 {
                currentMax = e1rm
                hasExerciseHistory = true
                // Set target weight to a reasonable goal (10% higher than current)
                targetWeight = (e1rm * 1.1).rounded()
            } else {
                hasExerciseHistory = false
            }
        } catch {
            print("Failed to fetch exercise history: \(error)")
            hasExerciseHistory = false
        }

        isLoadingHistory = false
    }

    private let apiClient = APIClient.shared

    func loadExercises() async {
        do {
            exercises = try await apiClient.getExercises()
            // Sort to show compound exercises first
            exercises.sort { ($0.category ?? "") < ($1.category ?? "") }
        } catch {
            print("Failed to load exercises: \(error)")
        }
    }

    func createGoal() async {
        guard let exercise = selectedExercise else { return }

        isCreating = true
        error = nil

        do {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"
            let deadlineString = dateFormatter.string(from: deadline)

            let goalCreate = GoalCreate(
                exerciseId: exercise.id,
                targetWeight: targetWeight,
                targetReps: targetReps,
                weightUnit: weightUnit,
                deadline: deadlineString,
                notes: nil
            )

            let _ = try await APIClient.shared.createGoal(goalCreate)
            goalCreated = true
        } catch {
            self.error = error.localizedDescription
        }

        isCreating = false
    }
}

#Preview {
    GoalSetupView()
}
