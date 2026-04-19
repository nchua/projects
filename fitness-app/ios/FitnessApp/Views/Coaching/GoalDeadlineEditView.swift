import SwiftUI

struct GoalDeadlineEditView: View {
    let goal: GoalSummaryResponse
    let onSaved: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var selectedDate: Date
    @State private var isSaving = false
    @State private var error: String?
    @State private var initialDateParseError: Bool = false

    private let originalDeadline: Date
    private let minimumDate: Date

    init(goal: GoalSummaryResponse, onSaved: @escaping () -> Void) {
        self.goal = goal
        self.onSaved = onSaved
        let minimum = Calendar.current.date(byAdding: .weekOfYear, value: 1, to: Date()) ?? Date()
        self.minimumDate = minimum
        if let parsed = DateFormatter.localDate.date(from: goal.deadline) {
            // Use parsed date as originalDeadline (unclamped). The DatePicker range
            // is widened below so it won't silently snap selectedDate.
            self._selectedDate = State(initialValue: parsed)
            self.originalDeadline = parsed
            self._initialDateParseError = State(initialValue: false)
        } else {
            // Unparseable server deadline — surface an error and block save.
            self._selectedDate = State(initialValue: minimum)
            self.originalDeadline = minimum
            self._initialDateParseError = State(initialValue: true)
        }
    }

    private var weeksRemaining: Int {
        let days = Calendar.current.dateComponents([.day], from: Date(), to: selectedDate).day ?? 0
        return max(0, days / 7)
    }

    private var originalWeeks: Int {
        let days = Calendar.current.dateComponents([.day], from: Date(), to: originalDeadline).day ?? 0
        return max(0, days / 7)
    }

    private var weeksDelta: Int {
        weeksRemaining - originalWeeks
    }

    private var hasChanged: Bool {
        !Calendar.current.isDate(selectedDate, inSameDayAs: originalDeadline)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.bgVoid.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        goalHeader

                        if initialDateParseError {
                            parseErrorBanner
                        }

                        quickAdjustSection

                        datePickerSection

                        deadlineSummary

                        if let error {
                            Text(error)
                                .font(.system(size: 13))
                                .foregroundColor(.warningRed)
                                .padding(.horizontal, 20)
                        }

                        saveButton
                    }
                    .padding(.vertical, 24)
                }
            }
            .navigationTitle("Edit Deadline")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.bgElevated, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .font(.system(size: 15))
                        .foregroundColor(.textSecondary)
                }
            }
        }
    }

    private var goalHeader: some View {
        HStack(spacing: 14) {
            Image(systemName: "target")
                .font(.system(size: 22))
                .foregroundColor(.systemPrimary)
                .frame(width: 44, height: 44)
                .background(Color.systemPrimary.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 12))

            VStack(alignment: .leading, spacing: 2) {
                Text(goal.exerciseName)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.white)

                Text("\(Int(goal.targetWeight)) \(goal.weightUnit) x \(goal.targetReps) \u{2022} \(Int(goal.progressPercent))% complete")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
            }

            Spacer()
        }
        .padding(16)
        .background(Color.bgCard)
        .cornerRadius(16)
        .padding(.horizontal, 20)
    }

    private var quickAdjustSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Quick Adjust (relative to current deadline)")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.textSecondary)
                .padding(.horizontal, 20)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    DeadlineChip(label: "Pull 2 wk", delta: -2, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                    DeadlineChip(label: "Pull 1 wk", delta: -1, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                    DeadlineChip(label: "Push 1 wk", delta: 1, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                    DeadlineChip(label: "Push 2 wk", delta: 2, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                    DeadlineChip(label: "Push 1 mo", delta: 4, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                    DeadlineChip(label: "Push 2 mo", delta: 8, selectedDate: $selectedDate, minimum: minimumDate, base: originalDeadline)
                }
                .padding(.horizontal, 20)
            }
        }
    }

    private var parseErrorBanner: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 14))
                .foregroundColor(.warningRed)
            Text("Couldn't read current deadline. Please refresh and try again.")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.warningRed)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(Color.warningRed.opacity(0.12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.warningRed.opacity(0.4), lineWidth: 1)
        )
        .cornerRadius(12)
        .padding(.horizontal, 20)
    }

    private var datePickerLowerBound: Date {
        // Widen the range to include originalDeadline if it's earlier than
        // minimumDate so SwiftUI doesn't silently snap selectedDate on first render.
        // Save-time validation enforces selectedDate >= minimumDate.
        min(originalDeadline, minimumDate)
    }

    private var datePickerSection: some View {
        DatePicker(
            "Target Date",
            selection: $selectedDate,
            in: datePickerLowerBound...,
            displayedComponents: .date
        )
        .datePickerStyle(.graphical)
        .tint(.systemPrimary)
        .colorScheme(.dark)
        .padding(20)
        .background(Color.bgCard)
        .cornerRadius(16)
        .padding(.horizontal, 20)
    }

    private var deadlineSummary: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("New Deadline")
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)

                Text(selectedDate, style: .date)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)

                HStack(spacing: 6) {
                    Text("\(weeksRemaining) weeks from now")
                        .font(.system(size: 14))
                        .foregroundColor(.systemPrimary)

                    if hasChanged && weeksDelta != 0 {
                        Text("(\(weeksDelta > 0 ? "+" : "")\(weeksDelta)w)")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(weeksDelta > 0 ? .successGreen : .gold)
                    }
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

    private var canSave: Bool {
        !initialDateParseError && hasChanged && !isSaving
    }

    private var saveButton: some View {
        Button {
            Task { await saveDeadline() }
        } label: {
            Group {
                if isSaving {
                    ProgressView()
                        .tint(.black)
                } else {
                    Text(hasChanged ? "Save Deadline" : "No Changes")
                }
            }
            .font(.system(size: 16, weight: .semibold))
            .foregroundColor(.black)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 18)
            .background(canSave ? Color.systemPrimary : Color.textMuted)
            .cornerRadius(50)
        }
        .disabled(!canSave)
        .padding(.horizontal, 20)
        .padding(.bottom, 20)
    }

    private func saveDeadline() async {
        // Validate: selected date must be on/after minimumDate (1 week out).
        if selectedDate < Calendar.current.startOfDay(for: minimumDate) {
            self.error = "Deadline must be at least 1 week from today."
            return
        }

        isSaving = true
        error = nil

        let update = GoalUpdate(
            targetWeight: nil,
            targetReps: nil,
            weightUnit: nil,
            deadline: DateFormatter.localDate.string(from: selectedDate),
            notes: nil
        )

        do {
            _ = try await APIClient.shared.updateGoal(id: goal.id, update)
            onSaved()
            dismiss()
        } catch {
            self.error = "Failed to update deadline: \(error.localizedDescription)"
        }

        isSaving = false
    }
}

private struct DeadlineChip: View {
    let label: String
    let targetDate: Date
    @Binding var selectedDate: Date
    let isDisabled: Bool

    init(label: String, delta: Int, selectedDate: Binding<Date>, minimum: Date, base: Date) {
        self.label = label
        self._selectedDate = selectedDate
        let target = Calendar.current.date(byAdding: .weekOfYear, value: delta, to: base) ?? base
        self.targetDate = target
        self.isDisabled = target < minimum
    }

    private var isSelected: Bool {
        Calendar.current.isDate(selectedDate, inSameDayAs: targetDate)
    }

    var body: some View {
        Button {
            selectedDate = targetDate
        } label: {
            Text(label)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(isSelected ? .black : isDisabled ? .textMuted : .white)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(isSelected ? Color.systemPrimary : Color.bgCard)
                .cornerRadius(50)
                .overlay(
                    RoundedRectangle(cornerRadius: 50)
                        .stroke(isSelected ? Color.clear : Color.white.opacity(0.1), lineWidth: 1)
                )
        }
        .disabled(isDisabled)
    }
}
