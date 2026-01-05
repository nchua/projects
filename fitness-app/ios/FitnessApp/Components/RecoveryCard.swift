import SwiftUI

/// Muscle recovery status card with Solo Leveling "System Window" styling
/// Shows which muscle groups are still recovering from recent workouts
struct RecoveryCard: View {
    let recoveryData: [MuscleRecoveryStatus]

    @State private var isExpanded = false

    /// Maximum hours remaining across all muscles
    var maxHoursRemaining: Int {
        recoveryData.map(\.hoursRemaining).max() ?? 0
    }

    /// Formatted max time remaining
    var maxTimeFormatted: String {
        if maxHoursRemaining >= 24 {
            let days = maxHoursRemaining / 24
            let hours = maxHoursRemaining % 24
            if hours > 0 {
                return "\(days)d \(hours)h"
            }
            return "\(days)d"
        }
        return "\(maxHoursRemaining)h"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Main card content
            Button {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                    isExpanded.toggle()
                }
            } label: {
                cardContent
            }
            .buttonStyle(PlainButtonStyle())

            // Expanded detail view
            if isExpanded {
                expandedContent
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(
            // Holographic gradient background
            LinearGradient(
                colors: [
                    Color.systemPrimary.opacity(0.08),
                    Color.voidDark.opacity(0.95)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(
            // Glowing border
            RoundedRectangle(cornerRadius: 2)
                .stroke(Color.systemPrimary, lineWidth: 1)
        )
        .overlay(
            // Top scanning line effect
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, .systemPrimary, .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 2)
                .opacity(0.6),
            alignment: .top
        )
        .clipShape(RoundedRectangle(cornerRadius: 2))
        .shadow(color: Color.systemPrimary.opacity(0.15), radius: 10, x: 0, y: 0)
    }

    // MARK: - Card Content

    private var cardContent: some View {
        VStack(spacing: 16) {
            // Header with icon and title
            HStack(spacing: 12) {
                // Lightning bolt icon in glowing circle
                ZStack {
                    Circle()
                        .stroke(Color.systemPrimary, lineWidth: 2)
                        .frame(width: 40, height: 40)
                        .shadow(color: Color.systemPrimary.opacity(0.5), radius: 8)

                    Image(systemName: "bolt.heart.fill")
                        .font(.system(size: 18))
                        .foregroundColor(.systemPrimary)
                }

                // Title and subtitle
                VStack(alignment: .leading, spacing: 2) {
                    Text("RECOVERY STATUS")
                        .font(.ariseHeader(size: 13, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .tracking(2)
                        .shadow(color: Color.systemPrimary.opacity(0.4), radius: 4)

                    Text("Muscle regeneration monitoring")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }

                Spacer()

                // Active badge
                Text("ACTIVE")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.systemPrimary)
                    .tracking(1)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.systemPrimary.opacity(0.1))
                    .overlay(
                        RoundedRectangle(cornerRadius: 2)
                            .stroke(Color.systemPrimary, lineWidth: 1)
                    )
                    .cornerRadius(2)

                // Expand chevron
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.textMuted)
            }

            // Muscle grid
            LazyVGrid(columns: gridColumns, spacing: 8) {
                ForEach(recoveryData) { muscle in
                    MuscleCell(muscle: muscle)
                }
            }
        }
        .padding(16)
    }

    private var gridColumns: [GridItem] {
        // Adjust columns based on count
        let count = min(recoveryData.count, 3)
        return Array(repeating: GridItem(.flexible(), spacing: 8), count: max(count, 2))
    }

    // MARK: - Expanded Content

    private var expandedContent: some View {
        VStack(spacing: 0) {
            // Divider
            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Detail rows for each muscle
            VStack(spacing: 0) {
                ForEach(recoveryData) { muscle in
                    MuscleDetailRow(muscle: muscle)

                    if muscle.id != recoveryData.last?.id {
                        Rectangle()
                            .fill(Color.ariseBorder.opacity(0.5))
                            .frame(height: 1)
                            .padding(.leading, 16)
                    }
                }
            }
        }
    }
}

// MARK: - Muscle Cell

struct MuscleCell: View {
    let muscle: MuscleRecoveryStatus

    var body: some View {
        VStack(spacing: 4) {
            Text(muscle.displayName.uppercased())
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textPrimary)
                .tracking(0.5)

            Text(muscle.timeRemainingFormatted)
                .font(.ariseDisplay(size: 14, weight: .bold))
                .foregroundColor(.systemPrimary)

            Text("\(Int(muscle.recoveryPercent))%")
                .font(.ariseMono(size: 9))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .padding(.horizontal, 8)
        .background(
            // Fill-up effect based on recovery percent
            GeometryReader { geo in
                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.systemPrimary.opacity(0.2),
                                Color.systemPrimary.opacity(0.05)
                            ],
                            startPoint: .bottom,
                            endPoint: .top
                        )
                    )
                    .frame(height: geo.size.height * (muscle.recoveryPercent / 100))
                    .frame(maxHeight: .infinity, alignment: .bottom)
            }
        )
        .background(Color.systemPrimary.opacity(0.05))
        .overlay(
            RoundedRectangle(cornerRadius: 0)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Muscle Detail Row

struct MuscleDetailRow: View {
    let muscle: MuscleRecoveryStatus

    @State private var showExercises = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Main row
            Button {
                withAnimation(.spring(response: 0.25, dampingFraction: 0.7)) {
                    showExercises.toggle()
                }
            } label: {
                HStack(spacing: 12) {
                    // Muscle info
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(muscle.displayName)
                                .font(.ariseHeader(size: 14, weight: .semibold))
                                .foregroundColor(.textPrimary)

                            Text("-")
                                .foregroundColor(.textMuted)

                            Text("\"\(muscle.fantasyName)\"")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                                .italic()
                        }

                        // Affected exercises summary
                        Text(exercisesSummary)
                            .font(.ariseMono(size: 10))
                            .foregroundColor(.textMuted)
                            .lineLimit(1)
                    }

                    Spacer()

                    // Time remaining
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(muscle.timeRemainingFormatted)
                            .font(.ariseDisplay(size: 16, weight: .bold))
                            .foregroundColor(.systemPrimary)

                        Text("REMAINING")
                            .font(.ariseMono(size: 8))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
                    }

                    // Expand indicator
                    if !muscle.affectedExercises.isEmpty {
                        Image(systemName: showExercises ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10))
                            .foregroundColor(.textMuted)
                    }
                }
            }
            .buttonStyle(PlainButtonStyle())

            // Progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.voidLight)
                        .frame(height: 4)

                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.systemPrimary)
                        .frame(width: geo.size.width * (muscle.recoveryPercent / 100), height: 4)
                }
            }
            .frame(height: 4)

            // Affected exercises (expanded)
            if showExercises && !muscle.affectedExercises.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("AFFECTED BY:")
                        .font(.ariseMono(size: 9, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                        .padding(.top, 4)

                    ForEach(muscle.affectedExercises) { exercise in
                        HStack(spacing: 8) {
                            Rectangle()
                                .fill(Color.exerciseColor(for: exercise.exerciseName))
                                .frame(width: 3, height: 16)
                                .cornerRadius(1)

                            Text(exercise.exerciseName)
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textSecondary)

                            Spacer()

                            Text(exercise.fatigueType.uppercased())
                                .font(.ariseMono(size: 9, weight: .medium))
                                .foregroundColor(exercise.fatigueType == "primary" ? .systemPrimary : .textMuted)
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.voidDark.opacity(0.3))
    }

    private var exercisesSummary: String {
        let names = muscle.affectedExercises.map(\.exerciseName)
        if names.isEmpty { return "" }
        if names.count <= 2 {
            return names.joined(separator: ", ")
        }
        return "\(names[0]), \(names[1]) +\(names.count - 2) more"
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        ScrollView {
            VStack(spacing: 24) {
                RecoveryCard(recoveryData: [
                    MuscleRecoveryStatus(
                        muscleGroup: "chest",
                        status: "recovering",
                        recoveryPercent: 35.0,
                        hoursRemaining: 36,
                        lastTrained: "2026-01-04T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "1",
                                exerciseName: "Bench Press",
                                workoutDate: "2026-01-04T10:00:00",
                                fatigueType: "primary"
                            ),
                            AffectedExercise(
                                exerciseId: "2",
                                exerciseName: "Incline Dumbbell Press",
                                workoutDate: "2026-01-04T10:00:00",
                                fatigueType: "primary"
                            )
                        ]
                    ),
                    MuscleRecoveryStatus(
                        muscleGroup: "triceps",
                        status: "recovering",
                        recoveryPercent: 45.0,
                        hoursRemaining: 20,
                        lastTrained: "2026-01-04T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "1",
                                exerciseName: "Bench Press",
                                workoutDate: "2026-01-04T10:00:00",
                                fatigueType: "secondary"
                            ),
                            AffectedExercise(
                                exerciseId: "3",
                                exerciseName: "Tricep Pushdowns",
                                workoutDate: "2026-01-04T10:00:00",
                                fatigueType: "primary"
                            )
                        ]
                    ),
                    MuscleRecoveryStatus(
                        muscleGroup: "shoulders",
                        status: "recovering",
                        recoveryPercent: 75.0,
                        hoursRemaining: 12,
                        lastTrained: "2026-01-04T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "1",
                                exerciseName: "Bench Press",
                                workoutDate: "2026-01-04T10:00:00",
                                fatigueType: "secondary"
                            )
                        ]
                    )
                ])
                .padding(.horizontal)

                // Empty state test
                Text("When all recovered, card is hidden")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
            }
            .padding(.vertical)
        }
    }
}
