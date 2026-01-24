import SwiftUI

/// Displays a superset group with multiple exercises and their sets
struct SupersetCard: View {
    let groupId: UUID
    let exercises: [LoggedExercise]
    let indices: [Int]
    @Binding var allExercises: [LoggedExercise]
    let onAddRound: (UUID) -> Void
    let onRemoveSuperset: (UUID) -> Void

    /// Number of rounds (based on the first exercise's set count)
    var roundCount: Int {
        exercises.first?.sets.count ?? 0
    }

    /// Check if a round is completed (all exercises have that set filled in)
    func isRoundCompleted(_ roundIndex: Int) -> Bool {
        for exercise in exercises {
            guard roundIndex < exercise.sets.count else { return false }
            let set = exercise.sets[roundIndex]
            if !((set.isBodyweight || set.weight > 0) && set.reps > 0) {
                return false
            }
        }
        return true
    }

    /// Total completed rounds
    var completedRounds: Int {
        (0..<roundCount).filter { isRoundCompleted($0) }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            SupersetHeader(
                exercises: exercises,
                completedRounds: completedRounds,
                totalRounds: roundCount,
                onRemove: { onRemoveSuperset(groupId) }
            )

            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Rounds
            ForEach(0..<roundCount, id: \.self) { roundIndex in
                SupersetRound(
                    roundNumber: roundIndex + 1,
                    exercises: exercises,
                    indices: indices,
                    roundIndex: roundIndex,
                    allExercises: $allExercises,
                    isCompleted: isRoundCompleted(roundIndex)
                )

                if roundIndex < roundCount - 1 {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                        .padding(.horizontal, 16)
                }
            }

            // Add Round Button
            Button {
                onAddRound(groupId)
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .bold))
                    Text("ADD ROUND")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .tracking(1)
                }
                .foregroundColor(.supersetPurple)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .background(Color.voidDark)
        }
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.supersetPurple.opacity(0.5), lineWidth: 2)
        )
        // Purple glow effect
        .shadow(color: Color.supersetPurpleGlow, radius: 8, x: 0, y: 0)
    }
}

// MARK: - Superset Header

struct SupersetHeader: View {
    let exercises: [LoggedExercise]
    let completedRounds: Int
    let totalRounds: Int
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            // Left superset indicator bar
            Rectangle()
                .fill(Color.supersetPurple)
                .frame(width: 4)

            HStack(spacing: 12) {
                // Superset icon and label
                HStack(spacing: 8) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.supersetPurple.opacity(0.2))
                            .frame(width: 32, height: 32)

                        Image(systemName: "link")
                            .font(.system(size: 14))
                            .foregroundColor(.supersetPurple)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("SUPERSET")
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(.supersetPurple)
                            .tracking(1)

                        // Exercise names
                        Text(exercises.map { $0.exerciseName }.joined(separator: " + "))
                            .font(.ariseHeader(size: 14, weight: .semibold))
                            .foregroundColor(.textPrimary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Progress indicator
                HStack(spacing: 4) {
                    Text("\(completedRounds)/\(totalRounds)")
                        .font(.ariseMono(size: 12, weight: .medium))
                        .foregroundColor(completedRounds == totalRounds ? .successGreen : .textSecondary)

                    Text("ROUNDS")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                // Menu
                Menu {
                    Button(role: .destructive, action: onRemove) {
                        Label("Remove Superset", systemImage: "trash")
                    }
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.voidLight)
                            .frame(width: 32, height: 32)

                        Image(systemName: "ellipsis")
                            .font(.system(size: 12))
                            .foregroundColor(.textSecondary)
                    }
                }
            }
            .padding(16)
        }
        .background(Color.voidMedium)
    }
}

// MARK: - Superset Round

struct SupersetRound: View {
    let roundNumber: Int
    let exercises: [LoggedExercise]
    let indices: [Int]
    let roundIndex: Int
    @Binding var allExercises: [LoggedExercise]
    let isCompleted: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Round header
            HStack {
                ZStack {
                    if isCompleted {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Color.successGreen)
                            .frame(width: 24, height: 24)
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.voidBlack)
                    } else {
                        Text("R\(roundNumber)")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(.supersetPurple)
                    }
                }

                Text("ROUND \(roundNumber)")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.voidDark.opacity(0.5))

            // Exercise inputs for this round
            ForEach(Array(zip(exercises, indices)), id: \.0.id) { exercise, exerciseIndex in
                if roundIndex < exercise.sets.count {
                    SupersetExerciseInput(
                        exerciseName: exercise.exerciseName,
                        exerciseColor: Color.exerciseColor(for: exercise.exerciseName),
                        set: $allExercises[exerciseIndex].sets[roundIndex]
                    )

                    if exercise.id != exercises.last?.id {
                        Rectangle()
                            .fill(Color.supersetPurple.opacity(0.2))
                            .frame(height: 1)
                            .padding(.leading, 48)
                    }
                }
            }
        }
        .background(isCompleted ? Color.successGreen.opacity(0.03) : Color.clear)
    }
}

// MARK: - Superset Exercise Input (Compact side-by-side)

struct SupersetExerciseInput: View {
    let exerciseName: String
    let exerciseColor: Color
    @Binding var set: LoggedSet

    var body: some View {
        HStack(spacing: 8) {
            // Exercise name indicator
            HStack(spacing: 8) {
                Rectangle()
                    .fill(exerciseColor)
                    .frame(width: 3, height: 28)

                Text(exerciseName)
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.textSecondary)
                    .lineLimit(1)
                    .frame(width: 80, alignment: .leading)
            }

            Spacer()

            // BW toggle
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    set.isBodyweight.toggle()
                    if set.isBodyweight {
                        set.weightText = ""
                    }
                }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(set.isBodyweight ? Color.systemPrimary.opacity(0.2) : Color.voidLight)
                        .frame(width: 28, height: 28)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(set.isBodyweight ? Color.systemPrimary : Color.ariseBorder, lineWidth: 1)
                        )

                    Text("BW")
                        .font(.ariseMono(size: 8, weight: .semibold))
                        .foregroundColor(set.isBodyweight ? .systemPrimary : .textMuted)
                }
            }

            // Weight input
            if !set.isBodyweight {
                HStack(spacing: 2) {
                    TextField("", text: $set.weightText)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.center)
                        .font(.ariseMono(size: 13, weight: .medium))
                        .foregroundColor(.textPrimary)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 4)
                        .background(Color.voidLight)
                        .cornerRadius(4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )
                        .frame(width: 56)

                    Text("lb")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)
                }
            } else {
                Text("BW")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .frame(width: 66)
            }

            // Reps input
            HStack(spacing: 2) {
                TextField("", text: $set.repsText)
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.center)
                    .font(.ariseMono(size: 13, weight: .medium))
                    .foregroundColor(.textPrimary)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 4)
                    .background(Color.voidLight)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
                    .frame(width: 44)

                Text("x")
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
            }

            // RPE (compact)
            AriseRPEMiniSelector(selectedRPE: $set.rpe)
                .frame(width: 36)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }
}
