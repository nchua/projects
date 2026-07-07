import SwiftUI
import Charts

struct StatusView: View {
    @Binding var selectedTab: Int
    @StateObject private var viewModel = StatusViewModel()
    @State private var questWorkoutId: String?  // For presenting a workout detail sheet
    @State private var showWeeklyReport = false

    var body: some View {
        NavigationStack {
            ZStack {
                // ARISE void background
                VoidBackground(glowIntensity: 0.02)

                ScrollView {
                    VStack(spacing: 16) {
                        // Load-error banner (partial failures across dashboard endpoints)
                        if viewModel.hasDataLoadErrors {
                            StatusDataErrorBanner(
                                summary: viewModel.dataLoadErrorSummary,
                                onRetry: {
                                    Task { await viewModel.loadData() }
                                },
                                onDismiss: {
                                    viewModel.dataLoadErrors = [:]
                                }
                            )
                            .padding(.horizontal, 20)
                        }

                        // 1. Hunter Header with XP (Edge Flow - gradient header)
                        HunterStatusHeader(
                            name: viewModel.hunterName,
                            initials: viewModel.hunterInitials,
                            rank: viewModel.hunterRank,
                            level: viewModel.hunterLevel,
                            currentXP: viewModel.currentXP,
                            xpToNextLevel: viewModel.xpToNextLevel,
                            levelProgress: viewModel.levelProgress,
                            streakDays: viewModel.streakDays,
                            onProfileTap: { selectedTab = 3 }  // Hunter tab
                        )
                        // No .padding(.horizontal) - full-width gradient header

                        // 2. Dashboard Card (weekly progress + CTA)
                        DashboardCard(
                            workouts: viewModel.weeklyReview?.totalWorkouts ?? 0,
                            workoutsGoal: viewModel.weeklyStats.workoutsGoal,
                            totalVolume: viewModel.weeklyStats.totalVolume,
                            activeMinutes: viewModel.weeklyStats.activeMinutes,
                            prsCount: viewModel.recentPRs.count
                        )
                        .padding(.horizontal, 20)

                        // 7. Power Levels (consolidated card)
                        PowerLevelsCard(lifts: viewModel.bigThreeLifts, selectedTab: $selectedTab)

                        // 7.5. Weekly Report Card
                        if viewModel.weeklyProgressReport != nil {
                            WeeklyReportCard(
                                totalWorkouts: viewModel.weeklyProgressReport?.totalWorkouts ?? 0,
                                weekDateRange: viewModel.weeklyReportDateRange,
                                overallStatus: viewModel.weeklyReportStatus,
                                onTap: { showWeeklyReport = true }
                            )
                            .padding(.horizontal, 20)
                        }

                        // 8. Recovery Status (Edge Flow - horizontal pills)
                        RecoveryStatusSection(cooldownData: viewModel.cooldownStatus)
                        // No .padding(.horizontal) - built into section

                        // Bottom padding for tab bar
                        Spacer().frame(height: 20)
                    }
                    .padding(.vertical)
                }
            }
            .navigationBarHidden(true)
            .refreshable {
                await viewModel.loadData()
            }
        }
        .task {
            await viewModel.loadData()
        }
        .sheet(isPresented: $showWeeklyReport) {
            WeeklyReportView()
        }
        .sheet(item: $questWorkoutId) { workoutId in
            WorkoutDetailSheet(workoutId: workoutId)
        }
    }
}

// Make String conform to Identifiable for sheet binding
extension String: @retroactive Identifiable {
    public var id: String { self }
}

// MARK: - Hunter Status Header (Edge Flow)

struct HunterStatusHeader: View {
    let name: String
    var initials: String = ""
    let rank: HunterRank
    let level: Int
    let currentXP: Int
    let xpToNextLevel: Int
    let levelProgress: Double
    let streakDays: Int
    var onProfileTap: (() -> Void)? = nil

    var avatarInitials: String {
        initials.isEmpty ? String(name.prefix(1)) : initials
    }

    var body: some View {
        VStack(spacing: 10) {
            // Top row: Avatar + Name + Level + Streak + XP
            HStack(spacing: 12) {
                // Hunter Avatar - Tappable for profile
                Button {
                    onProfileTap?()
                } label: {
                    EdgeFlowAvatar(initial: avatarInitials, rank: rank, size: 40)
                }
                .buttonStyle(PlainButtonStyle())
                .accessibilityLabel("Profile, \(rank.rawValue) rank")
                .accessibilityHint("Opens your profile")

                // Name and Meta - Tappable for profile
                Button {
                    onProfileTap?()
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(name)
                            .font(.ariseHeader(size: 20, weight: .bold))
                            .foregroundColor(Color(hex: "88DDFF"))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)

                        HStack(spacing: 10) {
                            Text("\(rank.rawValue)-Rank")
                                .foregroundColor(.systemPrimary)
                                .fontWeight(.semibold)

                            Text("Lv. \(level)")
                                .foregroundColor(.textSecondary)

                            if streakDays > 0 {
                                HStack(spacing: 3) {
                                    Image(systemName: "flame.fill")
                                        .foregroundColor(Color(hex: "FF9500"))
                                        .accessibilityHidden(true)
                                    Text("\(streakDays)")
                                }
                                .foregroundColor(Color(hex: "FF9500"))
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel("Streak: \(streakDays) \(streakDays == 1 ? "day" : "days")")
                            }
                        }
                        .font(.ariseMono(size: 12))
                    }
                }
                .buttonStyle(PlainButtonStyle())
                .accessibilityLabel("\(name), \(rank.rawValue) rank, level \(level)")
                .accessibilityHint("Opens your profile")

                Spacer()
            }

            // Inline XP Bar
            EdgeFlowXPBar(
                currentXP: currentXP,
                xpToNextLevel: xpToNextLevel,
                progress: levelProgress,
                level: level
            )
        }
        .padding(.horizontal, 20)
        .padding(.top, 50)  // Notch
        .padding(.bottom, 12)
        .background(
            LinearGradient(
                colors: [Color(hex: "141520"), Color(hex: "050508")],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }
}

// MARK: - Edge Flow Avatar

struct EdgeFlowAvatar: View {
    let initial: String
    let rank: HunterRank
    let size: CGFloat

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            // Avatar background
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(
                        LinearGradient(
                            colors: [Color(hex: "141520"), Color(hex: "0f1018")],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                Image(systemName: "figure.strengthtraining.traditional")
                    .font(.system(size: size * 0.4))
                    .foregroundColor(.systemPrimary)
            }
            .frame(width: size, height: size)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.systemPrimary.opacity(0.2), lineWidth: 1)
            )
            .shadow(color: Color.systemPrimary.opacity(0.3), radius: 10, x: 0, y: 0)

            // Rank badge
            Text(rank.rawValue)
                .font(.ariseMono(size: 10, weight: .bold))
                .foregroundColor(.black)
                .frame(width: 18, height: 18)
                .background(rank.color)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .offset(x: 4, y: 4)
        }
    }
}

// MARK: - Edge Flow XP Bar

struct EdgeFlowXPBar: View {
    let currentXP: Int
    let xpToNextLevel: Int
    let progress: Double
    let level: Int

    var body: some View {
        VStack(spacing: 6) {
            // Labels
            HStack {
                Text("Level \(level)")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)

                Spacer()

                Text("\(currentXP.formatted()) / \(xpToNextLevel.formatted()) XP")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
            }

            // Track - 4px slim bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // Background track
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.white.opacity(0.1))

                    // Fill with gradient
                    RoundedRectangle(cornerRadius: 2)
                        .fill(
                            LinearGradient(
                                colors: [Color.systemPrimary, Color(hex: "7B61FF")],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geometry.size.width * CGFloat(progress))
                        .shadow(color: Color.systemPrimary.opacity(0.4), radius: 5, x: 0, y: 0)
                }
            }
            .frame(height: 4)
        }
    }
}

// MARK: - Edge Flow Achievement Card

struct EdgeFlowAchievementCard: View {
    let pr: PRResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: pr.displayName)
    }

    var body: some View {
        HStack(spacing: 14) {
            // Trophy icon
            Image(systemName: "trophy.fill")
                .font(.system(size: 24))
                .foregroundColor(.gold)

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text("NEW PR")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(Color.gold.opacity(0.6))
                    .tracking(0.5)

                Text(pr.displayName)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)
            }

            Spacer()

            // Value
            if pr.prType == "e1rm", let value = pr.value {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text(value.formattedWeight)
                        .font(.ariseDisplay(size: 20, weight: .bold))
                        .foregroundColor(.gold)

                    Text("lb")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                }
            } else if let reps = pr.reps, let weight = pr.weight {
                Text("\(reps)\u{00D7}\(weight.formattedWeight)")
                    .font(.ariseDisplay(size: 20, weight: .bold))
                    .foregroundColor(.gold)
            }
        }
        .padding(16)
        .padding(.horizontal, 2)
        .background(Color.voidMedium)
        .clipShape(RoundedRectangle(cornerRadius: 20))
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.glassBorder, lineWidth: 1)
        )
        .shadow(color: Color.gold.opacity(0.05), radius: 15, x: 0, y: 0)
    }
}

// MARK: - Workout Detail Sheet

struct WorkoutDetailSheet: View {
    let workoutId: String

    @Environment(\.dismiss) private var dismiss
    @State private var workout: WorkoutResponse?
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(glowIntensity: 0.03)

                if isLoading {
                    VStack(spacing: 16) {
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Text("LOADING...")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(2)
                    }
                } else if let workout = workout {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            // Header Card
                            WorkoutSheetHeader(workout: workout)
                                .padding(.horizontal)

                            // Section Header
                            AriseSectionHeader(title: "Completed Objectives")
                                .padding(.horizontal)

                            // Exercises
                            ForEach(Array(workout.exercises.enumerated()), id: \.element.id) { index, exercise in
                                WorkoutExerciseCard(exercise: exercise)
                                    .padding(.horizontal)
                                    .fadeIn(delay: Double(index) * 0.05)
                            }
                        }
                        .padding(.vertical)
                    }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 32))
                            .foregroundColor(.warningRed)

                        Text(error ?? "Quest data not found")
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textSecondary)
                    }
                }
            }
            .navigationTitle("Quest Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                    .font(.ariseMono(size: 14, weight: .medium))
                    .foregroundColor(.systemPrimary)
                }
            }
        }
        .task {
            await loadWorkout()
        }
    }

    private func loadWorkout() async {
        isLoading = true
        do {
            workout = try await APIClient.shared.getWorkout(id: workoutId)
        } catch {
            self.error = "Failed to load quest: \(error.localizedDescription)"
        }
        isLoading = false
    }
}

struct WorkoutSheetHeader: View {
    let workout: WorkoutResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header with date and status
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("QUEST COMPLETED")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.successGreen)
                        .tracking(1)

                    Text(formatDate(workout.date))
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                }

                Spacer()

                // Completion checkmark
                ZStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.successGreen)
                        .frame(width: 40, height: 40)

                    Image(systemName: "checkmark")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.voidBlack)
                }
            }

            AriseDivider()

            // Stats row
            HStack(spacing: 24) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(workout.exercises.count)")
                        .font(.ariseDisplay(size: 20, weight: .bold))
                        .foregroundColor(.systemPrimary)
                    Text("OBJECTIVES")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(totalSets)")
                        .font(.ariseDisplay(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)
                    Text("SETS")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(0.5)
                }

                if let rpe = workout.sessionRpe {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(rpe)")
                            .font(.ariseDisplay(size: 20, weight: .bold))
                            .foregroundColor(.gold)
                        Text("RPE")
                            .font(.ariseMono(size: 9, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(0.5)
                    }
                }

                Spacer()
            }

            // Biometrics (avg/peak HR, strain, zone bar) — only when HR data exists;
            // degrades to nothing for legacy / non-HR workouts.
            if workout.hasHRData {
                AriseDivider()
                AriseWorkoutHRSection(workout: workout, title: "Biometrics")
            }

            // Notes
            if let notes = workout.notes, !notes.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("HUNTER NOTES")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)

                    Text(notes)
                        .font(.ariseMono(size: 13))
                        .foregroundColor(.textSecondary)
                        .italic()
                }
            }
        }
        .padding(20)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(Color.successGreen.opacity(0.3))
                .frame(height: 1),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }

    private var totalSets: Int {
        workout.exercises.reduce(0) { $0 + $1.sets.count }
    }

    private func formatDate(_ dateString: String) -> String {
        dateString.parseISO8601Date()?.formattedMedium ?? dateString
    }
}

struct WorkoutExerciseCard: View {
    let exercise: WorkoutExerciseResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: exercise.exerciseName)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: exercise.exerciseName)
    }

    var bestSet: SetResponse? {
        exercise.sets.max(by: { ($0.e1rm ?? 0) < ($1.e1rm ?? 0) })
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack(spacing: 0) {
                Rectangle()
                    .fill(exerciseColor)
                    .frame(width: 4)

                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(exercise.exerciseName)
                            .font(.ariseHeader(size: 16, weight: .semibold))
                            .foregroundColor(.textPrimary)

                        Text("\"\(fantasyName)\"")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)
                            .italic()
                    }

                    Spacer()

                    if let best = bestSet, let e1rm = best.e1rm {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("\(e1rm.formattedWeight)")
                                .font(.ariseDisplay(size: 18, weight: .bold))
                                .foregroundColor(.gold)
                            Text("BEST e1RM")
                                .font(.ariseMono(size: 8, weight: .semibold))
                                .foregroundColor(.textMuted)
                                .tracking(0.5)
                        }
                    }
                }
                .padding(16)
            }
            .background(Color.voidMedium)

            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Set Headers
            HStack {
                Text("SET")
                    .frame(width: 36, alignment: .leading)
                Text("WEIGHT")
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("REPS")
                    .frame(width: 44, alignment: .center)
                Text("RPE")
                    .frame(width: 36, alignment: .center)
                Text("e1RM")
                    .frame(width: 56, alignment: .trailing)
            }
            .font(.ariseMono(size: 10, weight: .semibold))
            .foregroundColor(.textMuted)
            .tracking(1)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.voidDark)

            // Sets
            ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                let isBest = bestSet?.id == set.id && set.e1rm != nil

                HStack {
                    ZStack {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.successGreen)
                            .frame(width: 20, height: 20)

                        Image(systemName: "checkmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.voidBlack)
                    }
                    .frame(width: 36, alignment: .leading)

                    Text("\(set.weight.formattedWeight) \(set.weightUnit)")
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundColor(.textPrimary)

                    Text("\(set.reps)")
                        .frame(width: 44, alignment: .center)
                        .foregroundColor(.textPrimary)

                    Text(set.rpe.map { "\($0)" } ?? "-")
                        .frame(width: 36, alignment: .center)
                        .foregroundColor(.systemPrimary)

                    Text(set.e1rm.map { "\($0.formattedWeight)" } ?? "-")
                        .frame(width: 56, alignment: .trailing)
                        .foregroundColor(isBest ? .gold : .textSecondary)
                }
                .font(.ariseMono(size: 14))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(isBest ? Color.gold.opacity(0.05) : Color.clear)

                if index < exercise.sets.count - 1 {
                    Rectangle()
                        .fill(Color.ariseBorder)
                        .frame(height: 1)
                        .padding(.horizontal, 16)
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

// MARK: - Weekly Report Card

struct WeeklyReportCard: View {
    let totalWorkouts: Int
    let weekDateRange: String
    let overallStatus: String  // "on_track" | "ahead" | "behind"
    let onTap: () -> Void

    private var statusLabel: String {
        switch overallStatus {
        case "ahead": return "AHEAD"
        case "behind": return "BEHIND"
        default: return "ON TRACK"
        }
    }

    private var statusColor: Color {
        switch overallStatus {
        case "ahead": return .gold
        case "behind": return .warningRed
        default: return .systemPrimary
        }
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                // Icon
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 20))
                    .foregroundColor(.systemPrimary)
                    .frame(width: 36, height: 36)
                    .background(Color.systemPrimary.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 2) {
                    Text("Weekly Report")
                        .font(.ariseHeader(size: 15, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    Text(weekDateRange)
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textSecondary)
                }

                Spacer()

                // Status badge
                Text(statusLabel)
                    .font(.ariseMono(size: 10, weight: .bold))
                    .foregroundColor(statusColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(statusColor.opacity(0.15))
                    .clipShape(Capsule())

                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(.textMuted)
            }
            .padding(14)
            .edgeFlowCard(accent: statusColor)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Home Data Error Banner

/// Compact banner shown at the top of StatusView when one or more dashboard
/// endpoints failed to load. Non-blocking — the rest of the dashboard still
/// renders from whatever data succeeded.
struct StatusDataErrorBanner: View {
    let summary: String
    let onRetry: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 14))
                .foregroundColor(.yellow)

            VStack(alignment: .leading, spacing: 2) {
                Text("Some data couldn't load")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .foregroundColor(.textPrimary)
                    .tracking(0.5)

                if !summary.isEmpty {
                    Text(summary)
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 8)

            Button(action: onRetry) {
                Text("Retry")
                    .font(.ariseMono(size: 11, weight: .semibold))
                    .tracking(1)
                    .foregroundColor(.voidBlack)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.yellow)
                    .cornerRadius(4)
            }

            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.textMuted)
                    .frame(width: 22, height: 22)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color.yellow.opacity(0.1))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.yellow.opacity(0.3), lineWidth: 1)
        )
    }
}

// MARK: - Preview

#Preview {
    StatusView(selectedTab: .constant(0))
        .environmentObject(AuthManager.shared)
}
