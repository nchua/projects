import SwiftUI
import Charts

struct HomeView: View {
    @StateObject private var viewModel = HomeViewModel()
    @State private var selectedInsight: InsightResponse?
    @State private var selectedWorkout: WorkoutSummaryResponse?

    // Hunter name from profile (could be enhanced to load from profile)
    private let hunterName = "Hunter"

    var body: some View {
        NavigationStack {
            ZStack {
                // ARISE void background
                VoidBackground(showGrid: true, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 24) {
                        // ARISE Hunter Header - Now using real data from viewModel
                        HunterStatusHeader(
                            name: hunterName,
                            rank: viewModel.hunterRank,
                            level: viewModel.hunterLevel,
                            currentXP: viewModel.currentXP,
                            xpToNextLevel: viewModel.xpToNextLevel,
                            levelProgress: viewModel.levelProgress,
                            streakDays: viewModel.streakDays
                        )
                        .padding(.horizontal)

                        // Daily Quests Card
                        if let quests = viewModel.dailyQuests, !quests.quests.isEmpty {
                            DailyQuestsCard(
                                quests: quests.quests,
                                refreshAt: quests.refreshAt,
                                onClaim: { questId in
                                    Task { await viewModel.claimQuest(questId) }
                                }
                            )
                            .padding(.horizontal)
                        }

                        // Weekly Quest Progress Card
                        WeeklyQuestCard(
                            workouts: viewModel.weeklyReview?.totalWorkouts ?? 0,
                            workoutsGoal: viewModel.weeklyStats.workoutsGoal,
                            volume: viewModel.weeklyStats.totalVolume,
                            activeMinutes: viewModel.weeklyStats.activeMinutes
                        )
                        .padding(.horizontal)

                        // Last Quest (Workout) Card
                        if let recentWorkout = viewModel.recentWorkout {
                            LastQuestCard(workout: recentWorkout) {
                                selectedWorkout = recentWorkout
                            }
                            .padding(.horizontal)
                        } else {
                            EmptyQuestCard()
                                .padding(.horizontal)
                        }

                        // Activity Rings (HealthKit)
                        if viewModel.healthKitAuthorized {
                            ActivityRingsCard(
                                steps: viewModel.todaySteps,
                                calories: viewModel.todayCalories,
                                exerciseMinutes: viewModel.todayExerciseMinutes,
                                standHours: viewModel.todayStandHours,
                                weeklySteps: viewModel.weeklySteps,
                                weeklyCalories: viewModel.weeklyCalories,
                                weeklyExerciseMinutes: viewModel.weeklyExerciseMinutes,
                                weeklyAvgSteps: viewModel.weeklyAvgSteps,
                                isSyncing: viewModel.isHealthKitSyncing,
                                onSync: {
                                    Task { await viewModel.syncHealthKit() }
                                }
                            )
                            .padding(.horizontal)
                        } else if HealthKitManager.shared.isHealthDataAvailable {
                            // Show connect button if HealthKit available but not authorized
                            HealthKitConnectCard {
                                Task { await viewModel.requestHealthKitAccess() }
                            }
                            .padding(.horizontal)
                        }

                        // Hunter Stats Section
                        AriseSectionHeader(title: "Hunter Stats")
                            .padding(.horizontal)

                        HunterStatsGrid(
                            workouts: viewModel.weeklyReview?.totalWorkouts ?? 0,
                            volume: viewModel.weeklyStats.totalVolume,
                            activeTime: viewModel.weeklyStats.activeMinutes,
                            prs: viewModel.weeklyReview?.prsAchieved.count ?? 0
                        )
                        .padding(.horizontal)

                        // Strength Trend Chart
                        if let trend = viewModel.primaryLiftTrend, !trend.dataPoints.isEmpty {
                            StrengthTrendCard(trend: trend)
                                .padding(.horizontal)
                        }

                        // Recent Achievements (PRs)
                        if !viewModel.recentPRs.isEmpty {
                            AriseSectionHeader(
                                title: "Achievements",
                                trailing: AnyView(
                                    Text("See All")
                                        .font(.ariseMono(size: 12))
                                        .foregroundColor(.systemPrimary)
                                )
                            )
                            .padding(.horizontal)

                            ForEach(viewModel.recentPRs.prefix(3)) { pr in
                                AchievementCard(pr: pr)
                                    .padding(.horizontal)
                            }
                        }

                        // System Insights
                        if !viewModel.insights.isEmpty {
                            AriseSectionHeader(title: "System Analysis")
                                .padding(.horizontal)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 12) {
                                    ForEach(viewModel.insights, id: \.title) { insight in
                                        SystemInsightCard(insight: insight, hasExercise: insight.exerciseId != nil) {
                                            if insight.exerciseId != nil {
                                                selectedInsight = insight
                                            }
                                        }
                                    }
                                }
                                .padding(.horizontal)
                            }
                        }

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
        .sheet(item: $selectedInsight) { insight in
            if let exerciseId = insight.exerciseId {
                ExerciseHistorySheet(
                    exerciseId: exerciseId,
                    exerciseName: insight.exerciseName ?? "Exercise"
                )
            }
        }
        .sheet(item: $selectedWorkout) { workout in
            WorkoutDetailSheet(workoutId: workout.id)
        }
    }
}

// MARK: - ARISE Hunter Status Header

struct HunterStatusHeader: View {
    let name: String
    let rank: HunterRank
    let level: Int
    let currentXP: Int
    let xpToNextLevel: Int
    let levelProgress: Double
    let streakDays: Int

    var body: some View {
        VStack(spacing: 16) {
            // Top row: Avatar + Name + Level
            HStack(spacing: 16) {
                // Hunter Avatar with Rank Badge
                HunterAvatarView(initial: String(name.prefix(1)), rank: rank, size: 60)

                // Name and Title
                VStack(alignment: .leading, spacing: 4) {
                    Text(name)
                        .font(.ariseHeader(size: 22, weight: .bold))
                        .foregroundColor(.textPrimary)

                    Text("\"\(rank.title)\"")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                        .italic()
                }

                Spacer()

                // Level Display
                VStack(spacing: 2) {
                    Text("\(level)")
                        .font(.ariseDisplay(size: 28, weight: .bold))
                        .foregroundColor(.systemPrimary)
                        .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)

                    Text("LEVEL")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }

                // Streak
                if streakDays > 0 {
                    StreakDisplayView(days: streakDays)
                }
            }

            // XP Bar - Now showing progress to next level
            XPBarView(current: currentXP, toNextLevel: xpToNextLevel, progress: levelProgress)

            // Date display with total XP
            HStack {
                Text("[ \(Date().formattedDayMonth.uppercased()) ]")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Spacer()

                Text("\(currentXP.formatted()) XP TOTAL")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.systemPrimary.opacity(0.7))
                    .tracking(0.5)
            }
        }
        .padding(16)
        .systemPanelStyle(hasGlow: true)
    }
}

// MARK: - Weekly Quest Card

struct WeeklyQuestCard: View {
    let workouts: Int
    let workoutsGoal: Int
    let volume: Double
    let activeMinutes: Int

    var questProgress: Double {
        guard workoutsGoal > 0 else { return 0 }
        return min(Double(workouts) / Double(workoutsGoal), 1.0)
    }

    var isComplete: Bool {
        workouts >= workoutsGoal
    }

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("[ WEEKLY QUEST ]")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(.systemPrimary)
                        .tracking(1)

                    Text("Complete \(workoutsGoal) Training Sessions")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)
                }

                Spacer()

                // Progress indicator
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(workouts)/\(workoutsGoal)")
                        .font(.ariseDisplay(size: 24, weight: .bold))
                        .foregroundColor(isComplete ? .successGreen : .systemPrimary)

                    Text("SESSIONS")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }
            }

            // Progress Bar
            AriseProgressBar(
                progress: questProgress,
                color: isComplete ? .successGreen : .systemPrimary,
                height: 12,
                showShimmer: !isComplete
            )

            // Stats row
            HStack(spacing: 24) {
                QuestStatItem(icon: "\u{1F4AA}", value: volume.formattedVolume, label: "Volume")
                QuestStatItem(icon: "\u{23F1}", value: "\(activeMinutes)", label: "Minutes")

                Spacer()

                if isComplete {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.successGreen)
                        Text("COMPLETE")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(.successGreen)
                    }
                }
            }
        }
        .padding(16)
        .systemPanelStyle(hasGlow: isComplete)
    }
}

struct QuestStatItem: View {
    let icon: String
    let value: String
    let label: String

    var body: some View {
        HStack(spacing: 6) {
            Text(icon)
                .font(.system(size: 14))

            VStack(alignment: .leading, spacing: 0) {
                Text(value)
                    .font(.ariseMono(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(label)
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
                    .textCase(.uppercase)
            }
        }
    }
}

// MARK: - Last Quest Card (Workout)

struct LastQuestCard: View {
    let workout: WorkoutSummaryResponse
    var onViewDetails: (() -> Void)? = nil

    // Get exercise names to display (up to 3), falling back to generic names if not available
    var exerciseNamesToShow: [String] {
        if let names = workout.exerciseNames, !names.isEmpty {
            return Array(names.prefix(3))
        } else {
            // Fallback to generic names if exercise_names not available
            return (0..<min(3, workout.exerciseCount)).map { "Exercise \($0 + 1)" }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    // Quest type badge
                    Text("[ COMPLETED QUEST ]")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(.successGreen)
                        .tracking(1)

                    Text("Training Session")
                        .font(.ariseHeader(size: 18, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Text("\(workout.exerciseCount) exercises completed")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(workout.totalSets)")
                        .font(.ariseDisplay(size: 28, weight: .bold))
                        .foregroundColor(.systemPrimary)
                        .shadow(color: .systemPrimaryGlow, radius: 8, x: 0, y: 0)

                    Text("SETS")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }
            }
            .padding(16)
            .background(Color.voidMedium)

            // Divider
            AriseDivider()

            // Exercise list preview
            VStack(spacing: 0) {
                ForEach(Array(exerciseNamesToShow.enumerated()), id: \.offset) { index, name in
                    HStack(spacing: 12) {
                        Rectangle()
                            .fill(Color.exerciseColor(for: name))
                            .frame(width: 3)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(name)
                                .font(.ariseHeader(size: 14, weight: .medium))
                                .foregroundColor(.textPrimary)

                            Text("\(workout.totalSets / max(workout.exerciseCount, 1)) sets")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(.textMuted)
                        }

                        Spacer()

                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 18))
                            .foregroundColor(.successGreen)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                }
            }
            .background(Color.voidDark)

            // View Details Button
            Button {
                onViewDetails?()
            } label: {
                HStack(spacing: 8) {
                    Text("VIEW DETAILS")
                        .font(.ariseHeader(size: 14, weight: .semibold))
                        .tracking(2)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundColor(.systemPrimary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.voidMedium)
            .overlay(
                Rectangle()
                    .stroke(Color.ariseBorder, lineWidth: 1)
            )
        }
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Empty Quest Card

struct EmptyQuestCard: View {
    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)

                Text("\u{2694}") // Crossed swords emoji
                    .font(.system(size: 28))
            }

            Text("No Active Quests")
                .font(.ariseHeader(size: 16, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text("Begin a training session to receive your daily quest")
                .font(.ariseMono(size: 12))
                .foregroundColor(.textMuted)
                .multilineTextAlignment(.center)

            Button(action: {}) {
                Text("START QUEST")
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .tracking(2)
            }
            .systemButtonStyle(isPrimary: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .padding(.horizontal, 24)
        .systemPanelStyle()
    }
}

// MARK: - Hunter Stats Grid

struct HunterStatsGrid: View {
    let workouts: Int
    let volume: Double
    let activeTime: Int
    let prs: Int

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            HunterStatCard(
                icon: "\u{2694}", // Crossed swords
                value: "\(workouts)",
                label: "Quests",
                change: "+1",
                isPositive: true
            )
            .fadeIn(delay: 0.0)

            HunterStatCard(
                icon: "\u{1F4AA}", // Flexed bicep
                value: volume.formattedVolume,
                label: "Volume",
                change: "+8%",
                isPositive: true
            )
            .fadeIn(delay: 0.1)

            HunterStatCard(
                icon: "\u{23F1}", // Stopwatch
                value: formatActiveTime(activeTime),
                label: "Time",
                change: "+23m",
                isPositive: true
            )
            .fadeIn(delay: 0.2)

            HunterStatCard(
                icon: "\u{1F3C6}", // Trophy
                value: "\(prs)",
                label: "PRs",
                change: "NEW!",
                isPositive: true
            )
            .fadeIn(delay: 0.3)
        }
    }

    private func formatActiveTime(_ minutes: Int) -> String {
        let hours = minutes / 60
        let mins = minutes % 60
        if hours > 0 {
            return "\(hours)h \(mins)m"
        }
        return "\(mins)m"
    }
}

struct HunterStatCard: View {
    let icon: String
    let value: String
    let label: String
    let change: String
    let isPositive: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Icon
            Text(icon)
                .font(.system(size: 20))

            // Value
            Text(value)
                .font(.ariseDisplay(size: 22, weight: .bold))
                .foregroundColor(.systemPrimary)
                .shadow(color: .systemPrimaryGlow.opacity(0.5), radius: 5, x: 0, y: 0)

            // Label
            Text(label)
                .font(.ariseMono(size: 11))
                .foregroundColor(.textMuted)
                .textCase(.uppercase)
                .tracking(0.5)

            // Change indicator
            HStack(spacing: 4) {
                Image(systemName: isPositive ? "arrow.up.right" : "arrow.down.right")
                    .font(.system(size: 10, weight: .bold))
                Text(change)
                    .font(.ariseMono(size: 10, weight: .medium))
            }
            .foregroundColor(isPositive ? .successGreen : .warningRed)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Strength Trend Card

struct StrengthTrendCard: View {
    let trend: LiftTrendResponse

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: trend.exerciseName)
    }

    var liftColor: Color {
        Color.exerciseColor(for: trend.exerciseName)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(trend.exerciseName)
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Text("\"\(fantasyName)\"")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                        .italic()
                }

                Spacer()

                AriseTrendBadge(direction: trend.trendDirection, percent: trend.percentChange)
            }

            AriseE1RMChart(dataPoints: trend.dataPoints)
                .frame(height: 120)
        }
        .padding(16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(liftColor)
                .frame(width: 3)
        }
    }
}

// MARK: - Achievement Card (PR)

struct AchievementCard: View {
    let pr: PRResponse

    var exerciseColor: Color {
        Color.exerciseColor(for: pr.exerciseName)
    }

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: pr.exerciseName)
    }

    var body: some View {
        HStack(spacing: 12) {
            // Left border
            Rectangle()
                .fill(exerciseColor)
                .frame(width: 3)

            // Trophy icon
            Text("\u{1F3C6}")
                .font(.system(size: 24))

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text(pr.exerciseName)
                    .font(.ariseHeader(size: 14, weight: .medium))
                    .foregroundColor(.textPrimary)

                Text("[ \(formatDate(pr.achievedAt).uppercased()) ]")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
                    .tracking(0.5)
            }

            Spacer()

            // Value
            VStack(alignment: .trailing, spacing: 2) {
                if pr.prType == "e1rm", let value = pr.value {
                    HStack(alignment: .lastTextBaseline, spacing: 4) {
                        Text(value.formattedWeight)
                            .font(.ariseDisplay(size: 20, weight: .bold))
                            .foregroundColor(.gold)

                        Text("lb")
                            .font(.ariseMono(size: 12))
                            .foregroundColor(.textMuted)
                    }

                    Text("E1RM")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                } else if let reps = pr.reps, let weight = pr.weight {
                    Text("\(reps) \u{00D7} \(weight.formattedWeight)")
                        .font(.ariseDisplay(size: 18, weight: .bold))
                        .foregroundColor(.gold)

                    Text("REP PR")
                        .font(.ariseMono(size: 9))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }
            }
        }
        .padding(.vertical, 12)
        .padding(.trailing, 16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.gold.opacity(0.3), lineWidth: 1)
        )
    }

    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: dateString) {
            return date.formattedMonthDay
        }
        return dateString
    }
}

// MARK: - System Insight Card

struct SystemInsightCard: View {
    let insight: InsightResponse
    var hasExercise: Bool = false
    var onTap: (() -> Void)? = nil

    var priorityColor: Color {
        switch insight.priority {
        case "high": return .warningRed
        case "medium": return .gold
        default: return .systemPrimary
        }
    }

    var priorityLabel: String {
        switch insight.priority {
        case "high": return "PRIORITY"
        case "medium": return "NOTICE"
        default: return "INFO"
        }
    }

    var body: some View {
        Button {
            onTap?()
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                // Priority tag
                HStack {
                    Text("[ \(priorityLabel) ]")
                        .font(.ariseMono(size: 9, weight: .medium))
                        .foregroundColor(priorityColor)
                        .tracking(1)

                    Spacer()

                    if hasExercise {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.textMuted)
                    }
                }

                Text(insight.title)
                    .font(.ariseHeader(size: 13, weight: .semibold))
                    .foregroundColor(.textPrimary)
                    .multilineTextAlignment(.leading)

                Text(insight.description)
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textSecondary)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)

                // Exercise name tag if available
                if let exerciseName = insight.exerciseName {
                    HStack(spacing: 4) {
                        Rectangle()
                            .fill(Color.exerciseColor(for: exerciseName))
                            .frame(width: 3, height: 12)
                            .cornerRadius(1)
                        Text(exerciseName)
                            .font(.ariseMono(size: 10, weight: .medium))
                            .foregroundColor(.systemPrimary)
                    }
                    .padding(.top, 4)
                }
            }
            .frame(width: 200, alignment: .leading)
            .padding(12)
            .background(Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(priorityColor.opacity(0.3), lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Exercise History Sheet

struct ExerciseHistorySheet: View {
    let exerciseId: String
    let exerciseName: String

    @Environment(\.dismiss) private var dismiss
    @State private var trend: TrendResponse?
    @State private var isLoading = true
    @State private var selectedTimeRange = "12w"

    let timeRanges = ["4w", "8w", "12w", "26w", "52w"]

    var exerciseColor: Color {
        Color.exerciseColor(for: exerciseName)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                if isLoading {
                    VStack(spacing: 16) {
                        SwiftUI.ProgressView()
                            .tint(.systemPrimary)
                        Text("LOADING...")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.textMuted)
                            .tracking(2)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 20) {
                            // Exercise Header
                            HStack(spacing: 0) {
                                Rectangle()
                                    .fill(exerciseColor)
                                    .frame(width: 4)

                                VStack(alignment: .leading, spacing: 4) {
                                    Text(exerciseName)
                                        .font(.ariseHeader(size: 20, weight: .bold))
                                        .foregroundColor(.textPrimary)

                                    Text("\"\(ExerciseFantasyNames.fantasyName(for: exerciseName))\"")
                                        .font(.ariseMono(size: 12))
                                        .foregroundColor(.textMuted)
                                        .italic()
                                }
                                .padding(.leading, 16)

                                Spacer()
                            }
                            .padding(16)
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                            .padding(.horizontal)

                            // Time Range Selector
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(timeRanges, id: \.self) { range in
                                        Button {
                                            selectedTimeRange = range
                                            Task {
                                                await loadTrend()
                                            }
                                        } label: {
                                            Text(timeRangeLabel(range))
                                                .font(.ariseMono(size: 12, weight: .semibold))
                                                .foregroundColor(selectedTimeRange == range ? .voidBlack : .textSecondary)
                                                .padding(.horizontal, 16)
                                                .padding(.vertical, 8)
                                                .background(selectedTimeRange == range ? Color.systemPrimary : Color.voidMedium)
                                                .cornerRadius(4)
                                        }
                                    }
                                }
                                .padding(.horizontal)
                            }

                            // Trend Data
                            if let trend = trend, !trend.dataPoints.isEmpty {
                                // Current E1RM Card
                                VStack(alignment: .leading, spacing: 16) {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("POWER LEVEL")
                                                .font(.ariseMono(size: 10, weight: .semibold))
                                                .foregroundColor(.textMuted)
                                                .tracking(1)

                                            if let current = trend.currentE1rm {
                                                HStack(alignment: .lastTextBaseline, spacing: 6) {
                                                    Text(current.formattedWeight)
                                                        .font(.ariseDisplay(size: 36, weight: .bold))
                                                        .foregroundColor(.systemPrimary)
                                                        .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)

                                                    Text("lb")
                                                        .font(.ariseMono(size: 14))
                                                        .foregroundColor(.textMuted)
                                                }
                                            }
                                        }

                                        Spacer()

                                        // Trend Badge
                                        VStack(alignment: .trailing, spacing: 4) {
                                            HStack(spacing: 4) {
                                                Image(systemName: trendIcon(trend.trendDirection))
                                                    .font(.system(size: 12, weight: .bold))
                                                if let percent = trend.percentChange {
                                                    Text("\(abs(percent), specifier: "%.1f")%")
                                                        .font(.ariseMono(size: 14, weight: .semibold))
                                                }
                                            }
                                            .foregroundColor(trendColor(trend.trendDirection))

                                            Text(trendLabel(trend.trendDirection))
                                                .font(.ariseMono(size: 9, weight: .medium))
                                                .foregroundColor(.textMuted)
                                                .tracking(1)
                                        }
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 8)
                                        .background(trendColor(trend.trendDirection).opacity(0.1))
                                        .cornerRadius(4)
                                    }

                                    // Chart
                                    AriseE1RMChart(dataPoints: trend.dataPoints)
                                        .frame(height: 180)
                                }
                                .padding(20)
                                .background(Color.voidMedium)
                                .overlay(
                                    Rectangle()
                                        .fill(exerciseColor.opacity(0.3))
                                        .frame(height: 1),
                                    alignment: .top
                                )
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.ariseBorder, lineWidth: 1)
                                )
                                .padding(.horizontal)

                                // Stats Summary
                                HStack(spacing: 12) {
                                    ExerciseStatBox(title: "QUESTS", value: "\(trend.totalWorkouts)")

                                    if let avg = trend.rollingAverage4w {
                                        ExerciseStatBox(title: "4W AVG", value: "\(avg.formattedWeight) lb")
                                    }
                                }
                                .padding(.horizontal)
                            } else {
                                // No Data
                                VStack(spacing: 16) {
                                    Image(systemName: "chart.bar.xaxis")
                                        .font(.system(size: 40))
                                        .foregroundColor(.textMuted)

                                    Text("No data available for this exercise yet.")
                                        .font(.ariseMono(size: 13))
                                        .foregroundColor(.textSecondary)
                                        .multilineTextAlignment(.center)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(40)
                                .background(Color.voidMedium)
                                .cornerRadius(4)
                                .padding(.horizontal)
                            }
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationTitle("Exercise History")
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
            await loadTrend()
        }
    }

    private func loadTrend() async {
        isLoading = true
        do {
            trend = try await APIClient.shared.getExerciseTrend(
                exerciseId: exerciseId,
                timeRange: selectedTimeRange
            )
        } catch {
            print("Failed to load trend: \(error)")
        }
        isLoading = false
    }

    private func timeRangeLabel(_ range: String) -> String {
        switch range {
        case "4w": return "4W"
        case "8w": return "8W"
        case "12w": return "12W"
        case "26w": return "6M"
        case "52w": return "1Y"
        default: return range
        }
    }

    private func trendIcon(_ direction: String) -> String {
        switch direction {
        case "improving": return "arrow.up.right"
        case "regressing": return "arrow.down.right"
        default: return "arrow.right"
        }
    }

    private func trendColor(_ direction: String) -> Color {
        switch direction {
        case "improving": return .successGreen
        case "regressing": return .warningRed
        default: return .textSecondary
        }
    }

    private func trendLabel(_ direction: String) -> String {
        switch direction {
        case "improving": return "RISING"
        case "regressing": return "FALLING"
        default: return "STABLE"
        }
    }
}

struct ExerciseStatBox: View {
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 6) {
            Text(title)
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(1)

            Text(value)
                .font(.ariseDisplay(size: 20, weight: .bold))
                .foregroundColor(.textPrimary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
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
                VoidBackground(showGrid: false, glowIntensity: 0.03)

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
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        if let date = formatter.date(from: dateString) {
            return date.formattedMedium
        }
        return dateString
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

// MARK: - Legacy Components (kept for compatibility)

struct SectionHeader: View {
    let title: String
    let action: String?

    var body: some View {
        AriseSectionHeader(
            title: title,
            trailing: action != nil ? AnyView(
                Text(action!)
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.systemPrimary)
            ) : nil
        )
    }
}

struct EmptyStateCard: View {
    let title: String
    let message: String
    let icon: String

    var body: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(Color.voidLight)
                    .frame(width: 64, height: 64)

                Image(systemName: icon)
                    .font(.system(size: 28))
                    .foregroundColor(.textMuted)
            }

            Text(title)
                .font(.ariseHeader(size: 16, weight: .semibold))
                .foregroundColor(.textPrimary)

            Text(message)
                .font(.ariseMono(size: 12))
                .foregroundColor(.textMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .systemPanelStyle()
    }
}

// Legacy aliases
struct PRCard: View {
    let pr: PRResponse
    var body: some View {
        AchievementCard(pr: pr)
    }
}

struct InsightCard: View {
    let insight: InsightResponse
    var body: some View {
        SystemInsightCard(insight: insight)
    }
}

struct QuickStatsGrid: View {
    let workouts: Int
    let volume: Double
    let activeTime: Int
    let prs: Int
    var body: some View {
        HunterStatsGrid(workouts: workouts, volume: volume, activeTime: activeTime, prs: prs)
    }
}

struct TodaysWorkoutCard: View {
    let workout: WorkoutSummaryResponse
    var body: some View {
        LastQuestCard(workout: workout)
    }
}

// MARK: - Activity Rings Card (HealthKit)

struct ActivityRingsCard: View {
    let steps: Int
    let calories: Int
    let exerciseMinutes: Int
    let standHours: Int
    var weeklySteps: Int = 0
    var weeklyCalories: Int = 0
    var weeklyExerciseMinutes: Int = 0
    var weeklyAvgSteps: Int = 0
    var isSyncing: Bool = false
    var onSync: (() -> Void)? = nil

    @State private var showWeekly = false

    // Goals
    private let stepsGoal = 10000
    private let caloriesGoal = 500
    private let exerciseGoal = 30
    private let standGoal = 12

    var body: some View {
        VStack(spacing: 16) {
            // Header with toggle
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(showWeekly ? "[ WEEKLY ACTIVITY ]" : "[ TODAY'S ACTIVITY ]")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(.systemPrimary)
                        .tracking(1)

                    Text("Apple Health Sync")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)
                }

                Spacer()

                // Toggle button
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showWeekly.toggle()
                    }
                } label: {
                    Text(showWeekly ? "7D" : "1D")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .foregroundColor(.voidBlack)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.systemPrimary)
                        .cornerRadius(4)
                }

                if isSyncing {
                    ProgressView()
                        .tint(.systemPrimary)
                        .scaleEffect(0.8)
                } else {
                    Button {
                        onSync?()
                    } label: {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(.systemPrimary)
                    }
                }
            }

            if showWeekly {
                // Weekly Stats
                VStack(spacing: 12) {
                    HStack(spacing: 16) {
                        WeeklyStatItem(
                            icon: "figure.walk",
                            iconColor: .green,
                            value: weeklySteps.formatted(),
                            label: "Total Steps"
                        )
                        WeeklyStatItem(
                            icon: "flame.fill",
                            iconColor: .red,
                            value: weeklyCalories.formatted(),
                            label: "Calories"
                        )
                    }
                    HStack(spacing: 16) {
                        WeeklyStatItem(
                            icon: "chart.bar.fill",
                            iconColor: .green,
                            value: weeklyAvgSteps.formatted(),
                            label: "Avg Steps/Day"
                        )
                        WeeklyStatItem(
                            icon: "figure.run",
                            iconColor: .orange,
                            value: "\(weeklyExerciseMinutes)m",
                            label: "Exercise"
                        )
                    }
                }
            } else {
                // Today's Stats Grid
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    ActivityStatItem(
                        icon: "figure.walk",
                        iconColor: .green,
                        value: steps.formatted(),
                        label: "Steps",
                        progress: min(Double(steps) / Double(stepsGoal), 1.0)
                    )

                    ActivityStatItem(
                        icon: "flame.fill",
                        iconColor: .red,
                        value: "\(calories)",
                        label: "Calories",
                        progress: min(Double(calories) / Double(caloriesGoal), 1.0)
                    )

                    ActivityStatItem(
                        icon: "figure.run",
                        iconColor: .green,
                        value: "\(exerciseMinutes)m",
                        label: "Exercise",
                        progress: min(Double(exerciseMinutes) / Double(exerciseGoal), 1.0)
                    )

                    ActivityStatItem(
                        icon: "figure.stand",
                        iconColor: .cyan,
                        value: "\(standHours)h",
                        label: "Stand",
                        progress: min(Double(standHours) / Double(standGoal), 1.0)
                    )
                }
            }
        }
        .padding(16)
        .systemPanelStyle()
    }
}

struct WeeklyStatItem: View {
    let icon: String
    let iconColor: Color
    let value: String
    let label: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 18, weight: .medium))
                .foregroundColor(iconColor)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(value)
                    .font(.ariseDisplay(size: 18, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text(label)
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
                    .textCase(.uppercase)
            }

            Spacer()
        }
        .padding(10)
        .background(Color.voidLight.opacity(0.3))
        .cornerRadius(4)
    }
}

struct ActivityStatItem: View {
    let icon: String
    let iconColor: Color
    let value: String
    let label: String
    let progress: Double

    var body: some View {
        HStack(spacing: 12) {
            // Icon with progress ring
            ZStack {
                Circle()
                    .stroke(iconColor.opacity(0.2), lineWidth: 3)
                    .frame(width: 36, height: 36)

                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(iconColor, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                    .frame(width: 36, height: 36)
                    .rotationEffect(.degrees(-90))

                Image(systemName: icon)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(iconColor)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(value)
                    .font(.ariseDisplay(size: 18, weight: .bold))
                    .foregroundColor(.textPrimary)

                Text(label)
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)
                    .textCase(.uppercase)
            }

            Spacer()
        }
        .padding(10)
        .background(Color.voidLight.opacity(0.3))
        .cornerRadius(4)
    }
}

struct HealthKitConnectCard: View {
    var onConnect: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "heart.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.red)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Connect Apple Health")
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Text("Sync steps, calories & activity rings")
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textMuted)
                }

                Spacer()
            }

            Button(action: onConnect) {
                Text("CONNECT")
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .tracking(2)
            }
            .systemButtonStyle(isPrimary: true)
        }
        .padding(16)
        .systemPanelStyle()
    }
}

// MARK: - Preview

#Preview {
    HomeView()
        .environmentObject(AuthManager.shared)
}
