import SwiftUI

/// Detail sheet shown when tapping a muscle group in recovery status
struct RecoveryDetailSheet: View {
    let muscle: MuscleCooldownStatus
    @Environment(\.dismiss) private var dismiss

    var isRecovered: Bool {
        muscle.hoursRemaining <= 0 || muscle.cooldownPercent >= 100
    }

    var statusColor: Color {
        isRecovered ? .successGreen : .warningRed
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 20) {
                        // Recovery Status Hero
                        recoveryHero
                            .padding(.horizontal)

                        // Last Session
                        lastSessionCard
                            .padding(.horizontal)

                        // Exercises
                        if !muscle.affectedExercises.isEmpty {
                            exercisesCard
                                .padding(.horizontal)
                        }

                        // Cooldown Calculation
                        if let breakdown = muscle.fatigueBreakdown {
                            calculationCard(breakdown: breakdown)
                                .padding(.horizontal)
                        }

                        Spacer(minLength: 40)
                    }
                    .padding(.vertical)
                }
            }
            .navigationTitle("\(muscle.displayName) Recovery")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.textSecondary)
                            .frame(width: 28, height: 28)
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                    }
                }
            }
        }
    }

    // MARK: - Recovery Hero

    private var recoveryHero: some View {
        HStack(spacing: 20) {
            // Recovery Ring
            ZStack {
                // Background circle
                Circle()
                    .stroke(Color.voidLight, lineWidth: 8)
                    .frame(width: 90, height: 90)

                // Progress ring
                Circle()
                    .trim(from: 0, to: min(muscle.cooldownPercent / 100, 1.0))
                    .stroke(
                        statusColor,
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .frame(width: 90, height: 90)
                    .rotationEffect(.degrees(-90))
                    .shadow(color: statusColor.opacity(0.5), radius: 8)

                // Center content
                VStack(spacing: 2) {
                    Text("\(Int(muscle.cooldownPercent))%")
                        .font(.ariseDisplay(size: 22, weight: .bold))
                        .foregroundColor(statusColor)

                    Text("RECOVERED")
                        .font(.ariseMono(size: 8))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }
            }

            // Muscle Info
            VStack(alignment: .leading, spacing: 6) {
                Text(muscle.displayName)
                    .font(.ariseHeader(size: 24, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text("\"\(muscle.fantasyName)\"")
                    .font(.ariseMono(size: 13))
                    .foregroundColor(.textMuted)
                    .italic()

                HStack(spacing: 4) {
                    if isRecovered {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.successGreen)
                        Text("Fully Recovered")
                            .foregroundColor(.successGreen)
                    } else {
                        Image(systemName: "clock.fill")
                            .foregroundColor(.warningRed)
                        Text("\(muscle.timeRemainingFormatted) remaining")
                            .foregroundColor(.warningRed)
                    }
                }
                .font(.ariseMono(size: 13, weight: .semibold))
            }

            Spacer()
        }
        .padding(20)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(statusColor.opacity(0.3), lineWidth: 1)
        )
    }

    // MARK: - Last Session Card

    private var lastSessionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("LAST SESSION")
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1.5)

            VStack(spacing: 0) {
                detailRow(label: "Trained", value: formatLastTrained(muscle.lastTrained))

                Rectangle()
                    .fill(Color.ariseBorder)
                    .frame(height: 1)

                detailRow(label: "Total Sets", value: "\(totalSets) sets")
            }
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
    }

    private var totalSets: Int {
        muscle.fatigueBreakdown?.totalSets ?? muscle.affectedExercises.count
    }

    private func detailRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.ariseMono(size: 13))
                .foregroundColor(.textSecondary)

            Spacer()

            Text(value)
                .font(.ariseMono(size: 13, weight: .semibold))
                .foregroundColor(.textPrimary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    // MARK: - Exercises Card

    private var exercisesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("EXERCISES THAT HIT \(muscle.displayName.uppercased())")
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1.5)

            VStack(spacing: 0) {
                ForEach(Array(muscle.affectedExercises.enumerated()), id: \.element.id) { index, exercise in
                    exerciseRow(exercise: exercise)

                    if index < muscle.affectedExercises.count - 1 {
                        Rectangle()
                            .fill(Color.ariseBorder)
                            .frame(height: 1)
                    }
                }
            }
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
    }

    private func exerciseRow(exercise: AffectedExercise) -> some View {
        HStack(spacing: 12) {
            // Color indicator
            Rectangle()
                .fill(Color.exerciseColor(for: exercise.exerciseName))
                .frame(width: 4, height: 36)
                .cornerRadius(2)

            // Exercise info
            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.exerciseName)
                    .font(.ariseHeader(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)

                Text(formatExerciseDate(exercise.workoutDate))
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
            }

            Spacer()

            // Primary/Secondary tag
            Text(exercise.fatigueType.uppercased())
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(exercise.fatigueType == "primary" ? .systemPrimary : .textMuted)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    exercise.fatigueType == "primary"
                        ? Color.systemPrimary.opacity(0.15)
                        : Color.voidLight
                )
                .cornerRadius(4)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    // MARK: - Calculation Card

    private func calculationCard(breakdown: FatigueBreakdown) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("COOLDOWN CALCULATION")
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1.5)

            VStack(spacing: 0) {
                calcRow(label: "Base cooldown (\(muscle.displayName))", value: "\(breakdown.baseCooldownHours)h")
                calcDivider
                calcRow(label: "Effective sets", value: String(format: "%.1f", breakdown.effectiveSets))
                calcDivider
                calcRow(label: "Intensity factor", value: String(format: "x%.2f", breakdown.avgIntensityFactor))
                calcDivider
                calcRow(label: "Volume multiplier", value: String(format: "x%.2f", breakdown.volumeMultiplier))
                calcDivider
                calcRow(label: "Age modifier", value: String(format: "x%.1f", breakdown.ageModifier))

                // Final calculation
                Rectangle()
                    .fill(Color.ariseBorder)
                    .frame(height: 1)
                    .padding(.vertical, 8)

                HStack {
                    Text("Final cooldown")
                        .font(.ariseMono(size: 14, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Spacer()

                    Text("\(breakdown.finalCooldownHours)h")
                        .font(.ariseDisplay(size: 18, weight: .bold))
                        .foregroundColor(.systemPrimary)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
            }
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
    }

    private func calcRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.ariseMono(size: 12))
                .foregroundColor(.textSecondary)

            Spacer()

            Text(value)
                .font(.ariseMono(size: 12, weight: .medium))
                .foregroundColor(.textPrimary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private var calcDivider: some View {
        Rectangle()
            .fill(Color.ariseBorder.opacity(0.5))
            .frame(height: 1)
            .padding(.leading, 14)
    }

    // MARK: - Formatting

    private func formatLastTrained(_ dateString: String) -> String {
        guard let date = dateString.parseISO8601Date() else {
            return dateString.formattedMonthDayFromISO
        }

        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            let formatter = DateFormatter()
            formatter.dateFormat = "h:mm a"
            return "Today, \(formatter.string(from: date))"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else {
            let days = calendar.dateComponents([.day], from: date, to: Date()).day ?? 0
            return "\(days) days ago"
        }
    }

    private func formatExerciseDate(_ dateString: String) -> String {
        dateString.formattedMonthDayFromISO
    }
}

// MARK: - Preview

#Preview {
    RecoveryDetailSheet(muscle: MuscleCooldownStatus(
        muscleGroup: "chest",
        status: "cooling",
        cooldownPercent: 35.0,
        hoursRemaining: 8,
        lastTrained: "2026-01-18T10:30:00",
        affectedExercises: [
            AffectedExercise(
                exerciseId: "1",
                exerciseName: "Bench Press",
                workoutDate: "2026-01-18T10:30:00",
                fatigueType: "primary"
            ),
            AffectedExercise(
                exerciseId: "2",
                exerciseName: "Incline DB Press",
                workoutDate: "2026-01-18T10:30:00",
                fatigueType: "primary"
            ),
            AffectedExercise(
                exerciseId: "3",
                exerciseName: "Cable Fly",
                workoutDate: "2026-01-18T10:30:00",
                fatigueType: "primary"
            )
        ],
        fatigueBreakdown: FatigueBreakdown(
            baseCooldownHours: 48,
            totalSets: 10,
            effectiveSets: 10.0,
            avgIntensityFactor: 1.15,
            volumeMultiplier: 1.2,
            ageModifier: 1.0,
            finalCooldownHours: 56
        )
    ))
}
