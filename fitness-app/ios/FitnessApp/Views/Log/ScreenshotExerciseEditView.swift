import SwiftUI

// MARK: - Editable models

/// Editable mirror of `ExtractedSet`. String-backed fields so TextField can be empty mid-edit.
struct EditableExtractedSet: Identifiable, Equatable {
    let id: UUID = UUID()
    var weightText: String
    var repsText: String
    var isWarmup: Bool
    /// Some sources bundle multiple identical sets as a single entry (e.g. "3x10 @ 135").
    /// We preserve but expose this so the user can expand or keep them grouped.
    var setsCount: Int

    var weightLb: Double { Double(weightText) ?? 0 }
    var reps: Int { Int(repsText) ?? 0 }

    init(from set: ExtractedSet) {
        self.weightText = set.weightLb == 0 ? "" : String(set.weightLb.cleanedForInput)
        self.repsText = set.reps == 0 ? "" : String(set.reps)
        self.isWarmup = set.isWarmup
        self.setsCount = max(1, set.sets)
    }

    /// Create a new blank set.
    init(weightText: String = "", repsText: String = "", isWarmup: Bool = false, setsCount: Int = 1) {
        self.weightText = weightText
        self.repsText = repsText
        self.isWarmup = isWarmup
        self.setsCount = setsCount
    }
}

/// Editable mirror of `ExtractedExercise`.
struct EditableExtractedExercise: Identifiable, Equatable {
    let id: UUID = UUID()
    /// Pulled from the original extraction; we keep it for display/fallback.
    var originalName: String
    var matchedExerciseId: String?
    var matchedExerciseName: String?
    var equipment: String?
    var sets: [EditableExtractedSet]

    var displayName: String {
        matchedExerciseName ?? originalName
    }

    var isMatched: Bool { matchedExerciseId != nil }

    init(from exercise: ExtractedExercise) {
        self.originalName = exercise.name
        self.matchedExerciseId = exercise.matchedExerciseId
        self.matchedExerciseName = exercise.matchedExerciseName
        self.equipment = exercise.equipment
        self.sets = exercise.sets.map { EditableExtractedSet(from: $0) }
    }
}

private extension Double {
    /// Strip trailing .0 for display in TextField — "135" not "135.0".
    var cleanedForInput: String {
        if self == Double(Int(self)) {
            return String(Int(self))
        }
        return String(self)
    }
}

// MARK: - Edit sheet

/// Edit sheet for a single extracted exercise from a screenshot. The user can:
/// - Change the matched exercise (searchable picker over `/exercises`)
/// - Edit each set's weight/reps/warmup flag
/// - Add a set
/// - Delete a set
/// - Delete the whole exercise (via the parent)
///
/// Per CLAUDE.md problem-solving guideline: when auto-extraction is wrong,
/// give the user manual control instead of burning another scan credit.
struct ScreenshotExerciseEditView: View {
    @Environment(\.dismiss) private var dismiss

    let exercises: [ExerciseResponse]          // Catalog to pick from
    @Binding var exercise: EditableExtractedExercise
    let onDeleteExercise: () -> Void

    @State private var showExercisePicker = false

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 20) {
                        matchedExerciseSection
                        setsSection
                        deleteSection
                    }
                    .padding()
                }
            }
            .navigationTitle("Edit Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.textMuted)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                        .font(.ariseMono(size: 14, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") {
                        UIApplication.shared.sendAction(
                            #selector(UIResponder.resignFirstResponder),
                            to: nil, from: nil, for: nil
                        )
                    }
                    .font(.ariseMono(size: 14, weight: .semibold))
                    .foregroundColor(.systemPrimary)
                }
            }
            .sheet(isPresented: $showExercisePicker) {
                ExerciseMatchPickerView(
                    exercises: exercises,
                    initialSelectionId: exercise.matchedExerciseId
                ) { picked in
                    exercise.matchedExerciseId = picked.id
                    exercise.matchedExerciseName = picked.name
                    showExercisePicker = false
                }
            }
        }
    }

    // MARK: - Matched exercise

    private var matchedExerciseSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("[ MATCHED EXERCISE ]")
                .font(.ariseMono(size: 10, weight: .medium))
                .foregroundColor(.systemPrimary)
                .tracking(1.5)

            Button {
                showExercisePicker = true
            } label: {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(exercise.displayName)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        HStack(spacing: 6) {
                            if exercise.isMatched {
                                Text("MATCHED")
                                    .font(.ariseMono(size: 9, weight: .semibold))
                                    .foregroundColor(.green)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.green.opacity(0.15))
                                    .cornerRadius(3)
                            } else {
                                Text("UNMATCHED")
                                    .font(.ariseMono(size: 9, weight: .semibold))
                                    .foregroundColor(.red)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.red.opacity(0.15))
                                    .cornerRadius(3)
                            }

                            if exercise.originalName != exercise.displayName {
                                Text("from \"\(exercise.originalName)\"")
                                    .font(.ariseMono(size: 10))
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }

                    Spacer()

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.textMuted)
                }
                .padding(14)
                .background(Color.voidMedium)
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.ariseBorder, lineWidth: 1)
                )
            }
        }
    }

    // MARK: - Sets

    private var setsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("[ SETS ]")
                    .font(.ariseMono(size: 10, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(1.5)
                Spacer()
                Button {
                    exercise.sets.append(EditableExtractedSet())
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "plus")
                            .font(.system(size: 11, weight: .bold))
                        Text("ADD SET")
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .tracking(1)
                    }
                    .foregroundColor(.systemPrimary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.systemPrimary.opacity(0.1))
                    .cornerRadius(4)
                }
            }

            if exercise.sets.isEmpty {
                Text("No sets. Tap ADD SET.")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textMuted)
                    .frame(maxWidth: .infinity)
                    .padding(20)
                    .background(Color.voidMedium)
                    .cornerRadius(6)
            } else {
                // Iterate by index so bindings are stable across deletes.
                ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, _ in
                    SetEditRow(
                        index: index + 1,
                        set: $exercise.sets[index],
                        onDelete: {
                            exercise.sets.remove(at: index)
                        }
                    )
                }
            }
        }
    }

    // MARK: - Delete exercise

    private var deleteSection: some View {
        Button(role: .destructive) {
            onDeleteExercise()
            dismiss()
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "trash")
                Text("Remove Exercise")
                    .font(.ariseMono(size: 13, weight: .semibold))
                    .tracking(1)
            }
            .foregroundColor(.red)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.red.opacity(0.08))
            .cornerRadius(6)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.red.opacity(0.3), lineWidth: 1)
            )
        }
    }
}

// MARK: - Set edit row

private struct SetEditRow: View {
    let index: Int
    @Binding var set: EditableExtractedSet
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            // Set number / warmup indicator
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(set.isWarmup ? Color.yellow.opacity(0.15) : Color.voidLight)
                    .frame(width: 32, height: 32)
                Text(set.isWarmup ? "W" : "\(index)")
                    .font(.ariseMono(size: 12, weight: .bold))
                    .foregroundColor(set.isWarmup ? .yellow : .textSecondary)
            }

            // Weight
            VStack(spacing: 2) {
                TextField("wt", text: $set.weightText)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.center)
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 4)
                    .background(Color.voidLight)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4).stroke(Color.ariseBorder, lineWidth: 1)
                    )
                Text("LB")
                    .font(.ariseMono(size: 8))
                    .foregroundColor(.textMuted)
            }
            .frame(maxWidth: .infinity)

            Text("×")
                .font(.ariseMono(size: 14))
                .foregroundColor(.textMuted)

            // Reps
            VStack(spacing: 2) {
                TextField("reps", text: $set.repsText)
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.center)
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 4)
                    .background(Color.voidLight)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4).stroke(Color.ariseBorder, lineWidth: 1)
                    )
                Text("REPS")
                    .font(.ariseMono(size: 8))
                    .foregroundColor(.textMuted)
            }
            .frame(maxWidth: .infinity)

            // Warmup toggle
            Button {
                set.isWarmup.toggle()
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(set.isWarmup ? Color.yellow.opacity(0.2) : Color.voidLight)
                        .frame(width: 32, height: 32)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(set.isWarmup ? Color.yellow : Color.ariseBorder, lineWidth: 1)
                        )
                    Image(systemName: "flame")
                        .font(.system(size: 12))
                        .foregroundColor(set.isWarmup ? .yellow : .textMuted)
                }
            }

            // Delete
            Button(action: onDelete) {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.textMuted)
                    .frame(width: 24, height: 32)
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(Color.voidMedium)
        .cornerRadius(6)
    }
}

// MARK: - Exercise match picker

/// Searchable picker for re-matching an extracted exercise to a catalog entry.
/// Scoped to this file so we don't collide with the existing `ExercisePickerView`.
struct ExerciseMatchPickerView: View {
    @Environment(\.dismiss) private var dismiss

    let exercises: [ExerciseResponse]
    let initialSelectionId: String?
    let onSelect: (ExerciseResponse) -> Void

    @State private var searchText: String = ""

    private var filtered: [ExerciseResponse] {
        guard !searchText.isEmpty else { return exercises }
        return exercises.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                VStack(spacing: 0) {
                    // Search
                    HStack(spacing: 10) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.textMuted)
                        TextField("Search exercises...", text: $searchText)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textPrimary)
                            .autocorrectionDisabled()
                        if !searchText.isEmpty {
                            Button { searchText = "" } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundColor(.textMuted)
                            }
                        }
                    }
                    .padding(12)
                    .background(Color.voidMedium)
                    .cornerRadius(6)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6).stroke(Color.ariseBorder, lineWidth: 1)
                    )
                    .padding()

                    // List
                    List {
                        ForEach(filtered) { ex in
                            Button {
                                onSelect(ex)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(ex.name)
                                            .font(.ariseHeader(size: 14, weight: .medium))
                                            .foregroundColor(.textPrimary)
                                        if let cat = ex.category {
                                            Text(cat.uppercased())
                                                .font(.ariseMono(size: 9, weight: .semibold))
                                                .foregroundColor(.textMuted)
                                                .tracking(1)
                                        }
                                    }
                                    Spacer()
                                    if ex.id == initialSelectionId {
                                        Image(systemName: "checkmark")
                                            .foregroundColor(.systemPrimary)
                                    }
                                }
                            }
                            .listRowBackground(Color.voidMedium)
                            .listRowSeparatorTint(Color.ariseBorder)
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                }
            }
            .navigationTitle("Pick Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.textMuted)
                }
            }
        }
    }
}
