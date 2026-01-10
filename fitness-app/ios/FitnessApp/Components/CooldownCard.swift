import SwiftUI

/// Muscle cooldown status card with Solo Leveling "System Window" styling
/// Shows which muscle groups are still cooling down from recent workouts
struct CooldownCard: View {
    let cooldownData: [MuscleCooldownStatus]
    var ageModifier: Double = 1.0

    @State private var isExpanded = false
    @State private var showingInfoSheet = false

    /// Maximum hours remaining across all muscles
    var maxHoursRemaining: Int {
        cooldownData.map(\.hoursRemaining).max() ?? 0
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
        .sheet(isPresented: $showingInfoSheet) {
            CooldownInfoSheet(ageModifier: ageModifier)
        }
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
                    Text("COOLDOWNS")
                        .font(.ariseHeader(size: 13, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .tracking(2)
                        .shadow(color: Color.systemPrimary.opacity(0.4), radius: 4)

                    Text("Muscle regeneration monitoring")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }

                Spacer()

                // Info button
                Button {
                    showingInfoSheet = true
                } label: {
                    Image(systemName: "info.circle")
                        .font(.system(size: 16))
                        .foregroundColor(.textMuted)
                }
                .buttonStyle(PlainButtonStyle())

                // Expand chevron
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.textMuted)
            }

            // Muscle grid
            LazyVGrid(columns: gridColumns, spacing: 8) {
                ForEach(cooldownData) { muscle in
                    CooldownMuscleCell(muscle: muscle)
                }
            }
        }
        .padding(16)
    }

    private var gridColumns: [GridItem] {
        // Adjust columns based on count
        let count = min(cooldownData.count, 3)
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
                ForEach(cooldownData) { muscle in
                    CooldownMuscleDetailRow(muscle: muscle)

                    if muscle.id != cooldownData.last?.id {
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

struct CooldownMuscleCell: View {
    let muscle: MuscleCooldownStatus

    var body: some View {
        VStack(spacing: 4) {
            Text(muscle.displayName.uppercased())
                .font(.ariseMono(size: 10, weight: .semibold))
                .foregroundColor(.textPrimary)
                .tracking(0.5)

            Text(muscle.timeRemainingFormatted)
                .font(.ariseDisplay(size: 14, weight: .bold))
                .foregroundColor(.systemPrimary)

            Text("\(Int(muscle.cooldownPercent))%")
                .font(.ariseMono(size: 9))
                .foregroundColor(.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .padding(.horizontal, 8)
        .background(
            // Fill-up effect based on cooldown percent
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
                    .frame(height: geo.size.height * (muscle.cooldownPercent / 100))
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

struct CooldownMuscleDetailRow: View {
    let muscle: MuscleCooldownStatus

    @State private var showStats = false

    /// Check if all exercises are secondary (indirect work)
    private var isSecondaryOnly: Bool {
        !muscle.affectedExercises.isEmpty &&
        muscle.affectedExercises.allSatisfy { $0.fatigueType == "secondary" }
    }

    /// Get intensity label from factor
    private var intensityLabel: String {
        guard let breakdown = muscle.fatigueBreakdown else { return "Moderate" }
        let factor = breakdown.avgIntensityFactor
        if factor < 0.85 { return "Light" }
        if factor < 1.15 { return "Moderate" }
        if factor < 1.45 { return "Heavy" }
        return "Max"
    }

    /// Get intensity percentage for bar (0-100)
    private var intensityPercent: Double {
        guard let breakdown = muscle.fatigueBreakdown else { return 50 }
        let factor = breakdown.avgIntensityFactor
        // Map 0.7-1.6 to 0-100
        let normalized = (factor - 0.7) / (1.6 - 0.7)
        return min(100, max(0, normalized * 100))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Main row - always visible
            Button {
                withAnimation(.spring(response: 0.25, dampingFraction: 0.7)) {
                    showStats.toggle()
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
                    Image(systemName: showStats ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10))
                        .foregroundColor(.textMuted)
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
                        .frame(width: geo.size.width * (muscle.cooldownPercent / 100), height: 4)
                }
            }
            .frame(height: 4)

            // Session Stats (expanded)
            if showStats {
                sessionStatsPanel
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.voidDark.opacity(0.3))
    }

    // MARK: - Session Stats Panel

    private var sessionStatsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Title
            HStack(spacing: 6) {
                Text(">")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.systemPrimary)
                Text("SESSION STATS")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.systemPrimary.opacity(0.8))
                    .tracking(1)
            }
            .padding(.top, 8)

            // Secondary muscle indicator (conditional)
            if isSecondaryOnly {
                secondaryMuscleTag
            }

            // Stats grid
            if let breakdown = muscle.fatigueBreakdown {
                statsGrid(breakdown: breakdown)
            }

            // Intensity bar
            intensityBar

            // Collapse indicator
            HStack {
                Spacer()
                HStack(spacing: 4) {
                    Image(systemName: "chevron.up")
                        .font(.system(size: 8))
                    Text("tap to collapse")
                        .font(.ariseMono(size: 9))
                }
                .foregroundColor(.systemPrimary.opacity(0.5))
                Spacer()
            }
            .padding(.top, 8)
        }
        .padding(.top, 8)
    }

    // MARK: - Secondary Muscle Tag

    private var secondaryMuscleTag: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.right")
                .font(.system(size: 10))
                .foregroundColor(.textMuted.opacity(0.6))

            Text("Indirect work from compound lifts")
                .font(.ariseMono(size: 10))
                .foregroundColor(.textMuted.opacity(0.8))
                .italic()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.textMuted.opacity(0.1))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.textMuted.opacity(0.2), lineWidth: 1)
        )
        .cornerRadius(6)
    }

    // MARK: - Stats Grid

    private func statsGrid(breakdown: FatigueBreakdown) -> some View {
        LazyVGrid(columns: [
            GridItem(.flexible(), spacing: 8),
            GridItem(.flexible(), spacing: 8)
        ], spacing: 8) {
            // Sets
            StatCell(label: "SETS", value: "\(breakdown.totalSets)")

            // Effective Sets
            StatCell(
                label: "EFFECTIVE",
                value: String(format: "%.1f", breakdown.effectiveSets),
                isHighlighted: breakdown.effectiveSets != Double(breakdown.totalSets)
            )

            // Base Cooldown
            StatCell(label: "BASE", value: "\(breakdown.baseCooldownHours)h")

            // Final Cooldown
            StatCell(
                label: "CALCULATED",
                value: "\(breakdown.finalCooldownHours)h",
                isHighlighted: breakdown.finalCooldownHours > breakdown.baseCooldownHours
            )
        }
    }

    // MARK: - Intensity Bar

    private var intensityBar: some View {
        VStack(spacing: 6) {
            HStack {
                Text("WORKOUT INTENSITY")
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)

                Spacer()

                Text(intensityLabel)
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.systemPrimary)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    // Background
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.voidLight.opacity(0.5))
                        .frame(height: 6)

                    // Fill with gradient
                    RoundedRectangle(cornerRadius: 3)
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color.systemPrimary.opacity(0.4),
                                    Color.systemPrimary.opacity(0.7),
                                    Color.systemPrimary
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * (intensityPercent / 100), height: 6)
                        .shadow(color: Color.systemPrimary.opacity(0.5), radius: 4)

                    // Marker at end
                    if intensityPercent > 5 {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Color.white)
                            .frame(width: 3, height: 10)
                            .shadow(color: Color.white.opacity(0.5), radius: 4)
                            .offset(x: geo.size.width * (intensityPercent / 100) - 3)
                    }
                }
            }
            .frame(height: 10)
        }
        .padding(.top, 8)
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

// MARK: - Stat Cell

struct StatCell: View {
    let label: String
    let value: String
    var isHighlighted: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.ariseMono(size: 8))
                .foregroundColor(.textMuted)
                .tracking(0.5)

            Text(value)
                .font(.ariseDisplay(size: 15, weight: .semibold))
                .foregroundColor(isHighlighted ? .systemPrimary : .textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(isHighlighted ? Color.systemPrimary.opacity(0.08) : Color.voidLight.opacity(0.3))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isHighlighted ? Color.systemPrimary.opacity(0.2) : Color.ariseBorder.opacity(0.5), lineWidth: 1)
        )
        .cornerRadius(6)
    }
}

// MARK: - Info Sheet

struct CooldownInfoSheet: View {
    let ageModifier: Double
    @Environment(\.dismiss) private var dismiss

    /// Get the age range description based on the modifier
    private var userAgeRange: String {
        switch ageModifier {
        case 1.0: return "Under 30"
        case 1.15: return "30-40"
        case 1.3: return "40-50"
        case 1.5: return "50+"
        default: return "Unknown"
        }
    }

    var body: some View {
        NavigationView {
            ZStack {
                Color.voidDark.ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        // Header explanation
                        VStack(alignment: .leading, spacing: 8) {
                            Text("About Cooldowns")
                                .font(.ariseHeader(size: 20, weight: .bold))
                                .foregroundColor(.textPrimary)

                            Text("Muscle recovery times are based on exercise science research. Your cooldown times are personalized based on your age.")
                                .font(.ariseMono(size: 13))
                                .foregroundColor(.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        // Base cooldown times
                        VStack(alignment: .leading, spacing: 12) {
                            Text("BASE RECOVERY TIMES")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.systemPrimary)
                                .tracking(1)

                            VStack(spacing: 8) {
                                cooldownRow(muscle: "Chest", hours: 72)
                                cooldownRow(muscle: "Hamstrings", hours: 72)
                                cooldownRow(muscle: "Quads", hours: 48)
                                cooldownRow(muscle: "Shoulders", hours: 48)
                                cooldownRow(muscle: "Biceps", hours: 36)
                                cooldownRow(muscle: "Triceps", hours: 36)
                            }
                        }
                        .padding(16)
                        .background(Color.voidLight.opacity(0.3))
                        .overlay(
                            RoundedRectangle(cornerRadius: 2)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                        // Age modifiers
                        VStack(alignment: .leading, spacing: 12) {
                            Text("AGE-BASED MODIFIERS")
                                .font(.ariseMono(size: 11, weight: .semibold))
                                .foregroundColor(.systemPrimary)
                                .tracking(1)

                            Text("Recovery time naturally increases with age. Your times are adjusted accordingly.")
                                .font(.ariseMono(size: 12))
                                .foregroundColor(.textMuted)

                            VStack(spacing: 8) {
                                ageModifierRow(range: "Under 30", modifier: 1.0, isActive: ageModifier == 1.0)
                                ageModifierRow(range: "30-40", modifier: 1.15, isActive: ageModifier == 1.15)
                                ageModifierRow(range: "40-50", modifier: 1.3, isActive: ageModifier == 1.3)
                                ageModifierRow(range: "50+", modifier: 1.5, isActive: ageModifier == 1.5)
                            }
                        }
                        .padding(16)
                        .background(Color.voidLight.opacity(0.3))
                        .overlay(
                            RoundedRectangle(cornerRadius: 2)
                                .stroke(Color.ariseBorder, lineWidth: 1)
                        )

                        // Current modifier callout
                        if ageModifier > 1.0 {
                            HStack(spacing: 12) {
                                Image(systemName: "person.fill")
                                    .font(.system(size: 20))
                                    .foregroundColor(.systemPrimary)

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Your Modifier: \(String(format: "%.0f%%", (ageModifier - 1) * 100)) longer")
                                        .font(.ariseMono(size: 13, weight: .semibold))
                                        .foregroundColor(.textPrimary)

                                    Text("Based on age range: \(userAgeRange)")
                                        .font(.ariseMono(size: 11))
                                        .foregroundColor(.textMuted)
                                }

                                Spacer()
                            }
                            .padding(16)
                            .background(Color.systemPrimary.opacity(0.1))
                            .overlay(
                                RoundedRectangle(cornerRadius: 2)
                                    .stroke(Color.systemPrimary.opacity(0.5), lineWidth: 1)
                            )
                        }

                        Spacer(minLength: 40)
                    }
                    .padding(20)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .foregroundColor(.systemPrimary)
                }
            }
        }
    }

    private func cooldownRow(muscle: String, hours: Int) -> some View {
        HStack {
            Text(muscle)
                .font(.ariseMono(size: 13))
                .foregroundColor(.textPrimary)

            Spacer()

            Text("\(hours) hours")
                .font(.ariseMono(size: 13, weight: .medium))
                .foregroundColor(.textSecondary)
        }
    }

    private func ageModifierRow(range: String, modifier: Double, isActive: Bool) -> some View {
        HStack {
            Text(range)
                .font(.ariseMono(size: 13))
                .foregroundColor(isActive ? .systemPrimary : .textPrimary)

            Spacer()

            if modifier == 1.0 {
                Text("Baseline")
                    .font(.ariseMono(size: 13, weight: .medium))
                    .foregroundColor(isActive ? .systemPrimary : .textSecondary)
            } else {
                Text("+\(Int((modifier - 1) * 100))%")
                    .font(.ariseMono(size: 13, weight: .medium))
                    .foregroundColor(isActive ? .systemPrimary : .textSecondary)
            }

            if isActive {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 14))
                    .foregroundColor(.systemPrimary)
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(isActive ? Color.systemPrimary.opacity(0.1) : Color.clear)
        .cornerRadius(4)
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        ScrollView {
            VStack(spacing: 24) {
                CooldownCard(cooldownData: [
                    MuscleCooldownStatus(
                        muscleGroup: "hamstrings",
                        status: "cooling",
                        cooldownPercent: 28.0,
                        hoursRemaining: 86,
                        lastTrained: "2026-01-09T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "1",
                                exerciseName: "Barbell Back Squat",
                                workoutDate: "2026-01-09T10:00:00",
                                fatigueType: "secondary"
                            ),
                            AffectedExercise(
                                exerciseId: "2",
                                exerciseName: "Romanian Deadlift",
                                workoutDate: "2026-01-09T10:00:00",
                                fatigueType: "primary"
                            )
                        ],
                        fatigueBreakdown: FatigueBreakdown(
                            baseCooldownHours: 72,
                            totalSets: 12,
                            effectiveSets: 8.5,
                            avgIntensityFactor: 1.3,
                            volumeMultiplier: 1.6,
                            ageModifier: 1.0,
                            finalCooldownHours: 120
                        )
                    ),
                    MuscleCooldownStatus(
                        muscleGroup: "quads",
                        status: "cooling",
                        cooldownPercent: 37.0,
                        hoursRemaining: 57,
                        lastTrained: "2026-01-09T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "1",
                                exerciseName: "Barbell Back Squat",
                                workoutDate: "2026-01-09T10:00:00",
                                fatigueType: "primary"
                            )
                        ],
                        fatigueBreakdown: FatigueBreakdown(
                            baseCooldownHours: 48,
                            totalSets: 7,
                            effectiveSets: 7.0,
                            avgIntensityFactor: 1.35,
                            volumeMultiplier: 1.42,
                            ageModifier: 1.0,
                            finalCooldownHours: 91
                        )
                    ),
                    MuscleCooldownStatus(
                        muscleGroup: "biceps",
                        status: "cooling",
                        cooldownPercent: 93.0,
                        hoursRemaining: 2,
                        lastTrained: "2026-01-09T10:00:00",
                        affectedExercises: [
                            AffectedExercise(
                                exerciseId: "3",
                                exerciseName: "Barbell Row",
                                workoutDate: "2026-01-09T10:00:00",
                                fatigueType: "secondary"
                            )
                        ],
                        fatigueBreakdown: FatigueBreakdown(
                            baseCooldownHours: 36,
                            totalSets: 4,
                            effectiveSets: 2.0,
                            avgIntensityFactor: 1.0,
                            volumeMultiplier: 1.0,
                            ageModifier: 1.0,
                            finalCooldownHours: 36
                        )
                    )
                ])
                .padding(.horizontal)

                // Empty state test
                Text("When all cooled down, card is hidden")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
            }
            .padding(.vertical)
        }
    }
}
