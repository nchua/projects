import SwiftUI

/// Exercise selection modal for creating supersets (2+ exercises)
struct SupersetPickerView: View {
    @ObservedObject var viewModel: LogViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var selectedExercises: [ExerciseResponse] = []

    /// Minimum exercises required for a superset
    private let minExercises = 2

    let onComplete: ([ExerciseResponse]) -> Void

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Exercise count indicator
                    ExerciseCountIndicator(count: selectedExercises.count, minimum: minExercises)
                        .padding(.vertical, 16)

                    // Selected exercises preview
                    if !selectedExercises.isEmpty {
                        SelectedExercisesPreview(exercises: selectedExercises) { index in
                            selectedExercises.remove(at: index)
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 16)
                    }

                    // Search Bar
                    HStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.textMuted)

                        TextField("Search exercises...", text: $viewModel.searchText)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textPrimary)

                        if !viewModel.searchText.isEmpty {
                            Button {
                                viewModel.searchText = ""
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }
                    .padding(14)
                    .background(Color.voidMedium)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
                    .padding(.horizontal)

                    // Category Filter
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            AriseCategoryChip(
                                title: "ALL",
                                isSelected: viewModel.selectedCategory == nil
                            ) {
                                viewModel.selectedCategory = nil
                            }

                            ForEach(viewModel.categories, id: \.self) { category in
                                AriseCategoryChip(
                                    title: category.uppercased(),
                                    isSelected: viewModel.selectedCategory == category
                                ) {
                                    viewModel.selectedCategory = category
                                }
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.vertical, 16)

                    // Instruction text
                    Text(selectedExercises.count < minExercises
                        ? "Select at least \(minExercises) exercises"
                        : "Add more exercises or tap Done")
                        .font(.ariseMono(size: 12, weight: .medium))
                        .foregroundColor(.textSecondary)
                        .padding(.bottom, 8)

                    // Exercise List
                    if viewModel.isLoading {
                        Spacer()
                        ProgressView()
                            .tint(.systemPrimary)
                        Spacer()
                    } else {
                        List {
                            ForEach(viewModel.filteredExercises) { exercise in
                                let isSelected = selectedExercises.contains { $0.id == exercise.id }
                                Button {
                                    selectExercise(exercise)
                                } label: {
                                    SupersetExerciseRow(
                                        exercise: exercise,
                                        isSelected: isSelected,
                                        stepNumber: isSelected ? (selectedExercises.firstIndex { $0.id == exercise.id }.map { $0 + 1 }) : nil
                                    )
                                }
                                .disabled(isSelected)
                                .listRowBackground(Color.voidMedium)
                                .listRowSeparatorTint(Color.ariseBorder)
                            }
                        }
                        .listStyle(.plain)
                        .scrollContentBackground(.hidden)
                    }
                }
            }
            .navigationTitle("Create Superset")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        viewModel.searchText = ""
                        viewModel.selectedCategory = nil
                        dismiss()
                    }
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.textSecondary)
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        viewModel.searchText = ""
                        viewModel.selectedCategory = nil
                        onComplete(selectedExercises)
                        dismiss()
                    }
                    .font(.ariseMono(size: 14, weight: .semibold))
                    .foregroundColor(selectedExercises.count >= minExercises ? .supersetPurple : .textMuted)
                    .disabled(selectedExercises.count < minExercises)
                }
            }
        }
    }

    private func selectExercise(_ exercise: ExerciseResponse) {
        withAnimation(.quickSpring) {
            selectedExercises.append(exercise)
        }
    }
}

// MARK: - Exercise Count Indicator

struct ExerciseCountIndicator: View {
    let count: Int
    let minimum: Int

    var body: some View {
        HStack(spacing: 12) {
            // Count circle
            ZStack {
                Circle()
                    .fill(count >= minimum ? Color.supersetPurple : Color.voidLight)
                    .frame(width: 36, height: 36)

                Text("\(count)")
                    .font(.ariseMono(size: 16, weight: .bold))
                    .foregroundColor(count >= minimum ? .white : .textMuted)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("EXERCISES SELECTED")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Text(count >= minimum ? "Ready to create superset" : "Need \(minimum - count) more")
                    .font(.ariseMono(size: 12, weight: .medium))
                    .foregroundColor(count >= minimum ? .supersetPurple : .textSecondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.supersetPurple.opacity(count >= minimum ? 0.1 : 0.05))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.supersetPurple.opacity(count >= minimum ? 0.3 : 0.1), lineWidth: 1)
        )
    }
}

// MARK: - Selected Exercises Preview

struct SelectedExercisesPreview: View {
    let exercises: [ExerciseResponse]
    let onRemove: (Int) -> Void

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "link")
                    .font(.system(size: 12))
                    .foregroundColor(.supersetPurple)

                Text("SUPERSET • \(exercises.count) EXERCISES")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.supersetPurple)
                    .tracking(1)

                Spacer()
            }

            // Scrollable for 3+ exercises
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(exercises.enumerated()), id: \.element.id) { index, exercise in
                        HStack(spacing: 8) {
                            Rectangle()
                                .fill(Color.exerciseColor(for: exercise.name))
                                .frame(width: 3, height: 32)

                            Text(exercise.name)
                                .font(.ariseMono(size: 12, weight: .medium))
                                .foregroundColor(.textPrimary)
                                .lineLimit(1)

                            Button {
                                withAnimation(.quickSpring) {
                                    onRemove(index)
                                }
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 14))
                                    .foregroundColor(.textMuted)
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color.voidMedium)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.supersetPurple.opacity(0.3), lineWidth: 1)
                        )

                        if index < exercises.count - 1 {
                            Image(systemName: "plus")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(.supersetPurple)
                        }
                    }
                }
            }
        }
        .padding(12)
        .background(Color.supersetPurple.opacity(0.1))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.supersetPurple.opacity(0.3), lineWidth: 1)
        )
    }
}

// MARK: - Superset Exercise Row

struct SupersetExerciseRow: View {
    let exercise: ExerciseResponse
    let isSelected: Bool
    let stepNumber: Int?

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.name)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Color indicator
            Rectangle()
                .fill(exerciseColor)
                .frame(width: 4, height: 50)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(exercise.name)
                        .font(.ariseHeader(size: 15, weight: .medium))
                        .foregroundColor(isSelected ? .textMuted : .textPrimary)

                    HStack(spacing: 8) {
                        Text((exercise.category ?? "OTHER").uppercased())
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(isSelected ? exerciseColor.opacity(0.5) : exerciseColor)
                            .tracking(0.5)

                        if let muscle = exercise.primaryMuscle {
                            Circle()
                                .fill(Color.textMuted)
                                .frame(width: 3, height: 3)

                            Text(muscle.capitalized)
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textSecondary)
                        }
                    }
                }

                Spacer()

                if isSelected, let step = stepNumber {
                    // Selected indicator
                    ZStack {
                        Circle()
                            .fill(Color.supersetPurple)
                            .frame(width: 32, height: 32)

                        Text("\(step)")
                            .font(.ariseMono(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    }
                } else {
                    // Add button
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.supersetPurple.opacity(0.1))
                            .frame(width: 32, height: 32)

                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.supersetPurple)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .opacity(isSelected ? 0.6 : 1.0)
    }
}

// MARK: - Color Extension

extension Color {
    static let supersetPurple = Color(red: 0.6, green: 0.4, blue: 0.9)
    static let supersetPurpleGlow = Color(red: 0.6, green: 0.4, blue: 0.9).opacity(0.5)
}
