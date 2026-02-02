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
                    ProgressStepsIndicator(currentStep: viewModel.currentStep, totalSteps: 4)
                        .padding(.top, 20)
                        .padding(.horizontal, 20)

                    // Step Content
                    TabView(selection: $viewModel.currentStep) {
                        Step1ExerciseSelection(viewModel: viewModel)
                            .tag(1)

                        Step2TargetWeight(viewModel: viewModel)
                            .tag(2)

                        Step3Deadline(viewModel: viewModel)
                            .tag(3)

                        Step4Confirmation(viewModel: viewModel, onComplete: {
                            dismiss()
                        })
                            .tag(4)
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

    var filteredExercises: [ExerciseResponse] {
        if searchText.isEmpty {
            return viewModel.exercises
        }
        return viewModel.exercises.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
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
                        }
                    }
                }
                .padding(.horizontal, 20)
            }

            // Continue Button
            Button {
                isSearchFocused = false  // Dismiss keyboard
                viewModel.currentStep = 2
            } label: {
                Text("Continue")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 18)
                    .background(
                        viewModel.selectedExercise != nil
                            ? Color.systemPrimary
                            : Color.white.opacity(0.1)
                    )
                    .cornerRadius(50)
            }
            .disabled(viewModel.selectedExercise == nil)
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

// MARK: - Step 2: Target Weight

struct Step2TargetWeight: View {
    @ObservedObject var viewModel: GoalSetupViewModel

    var body: some View {
        VStack(spacing: 24) {
            // Title
            VStack(alignment: .leading, spacing: 8) {
                Text("Set Your Target")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(.white)

                Text("What weight do you want to hit on \(viewModel.selectedExercise?.name ?? "this exercise")?")
                    .font(.system(size: 15))
                    .foregroundColor(.textSecondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20)

            Spacer()

            // Weight Display
            VStack(spacing: 8) {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text("\(Int(viewModel.targetWeight))")
                        .font(.system(size: 72, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    Text(viewModel.weightUnit)
                        .font(.system(size: 24))
                        .foregroundColor(.textSecondary)
                }

                if let currentMax = viewModel.currentMax {
                    Text("Your current max: \(Int(currentMax)) \(viewModel.weightUnit)")
                        .font(.system(size: 14))
                        .foregroundColor(.textSecondary)
                }
            }

            // Weight Controls
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
            .padding(.top, 16)

            Spacer()

            // Progress needed
            if let currentMax = viewModel.currentMax, viewModel.targetWeight > currentMax {
                let diff = viewModel.targetWeight - currentMax
                let percent = (diff / currentMax) * 100

                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Progress needed")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)

                        Text("+\(Int(diff)) \(viewModel.weightUnit) (+\(String(format: "%.1f", percent))%)")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(.white)
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
                viewModel.currentStep = 3
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

// MARK: - Step 3: Deadline

struct Step3Deadline: View {
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

                Text("When do you want to hit \(Int(viewModel.targetWeight)) \(viewModel.weightUnit) on \(viewModel.selectedExercise?.name ?? "this exercise")?")
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

// MARK: - Step 4: Confirmation

struct Step4Confirmation: View {
    @ObservedObject var viewModel: GoalSetupViewModel
    let onComplete: () -> Void

    var weeksRemaining: Int {
        let days = Calendar.current.dateComponents([.day], from: Date(), to: viewModel.deadline).day ?? 0
        return max(0, days / 7)
    }

    var progressNeeded: Double {
        guard let currentMax = viewModel.currentMax, currentMax > 0 else { return 0 }
        return viewModel.targetWeight - currentMax
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
                            }
                        }

                        Spacer()
                    }

                    // Details
                    VStack(spacing: 0) {
                        GoalDetailRow(label: "Current Max", value: viewModel.currentMax != nil ? "\(Int(viewModel.currentMax!)) \(viewModel.weightUnit)" : "Unknown")

                        Divider().background(Color.white.opacity(0.05))

                        GoalDetailRow(label: "Progress Needed", value: "+\(Int(progressNeeded)) \(viewModel.weightUnit)", isHighlight: true)

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
    @Published var weightUnit: String = "lb"
    @Published var deadline: Date = Calendar.current.date(byAdding: .month, value: 2, to: Date()) ?? Date()
    @Published var currentMax: Double?
    @Published var isCreating = false
    @Published var goalCreated = false
    @Published var error: String?

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
