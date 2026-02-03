import SwiftUI

/// Mission card displayed on Home tab - shows current weekly mission status
/// Four states: loading, error, empty (create goal), ready (accept mission), active (in progress)
struct MissionCard: View {
    let missionData: CurrentMissionResponse?
    var missionLoadError: String? = nil
    let onCreateGoal: () -> Void
    let onAcceptMission: (String) -> Void
    let onViewMission: (String) -> Void
    var onRetry: (() -> Void)? = nil  // For retrying after error
    var onAddGoal: (() -> Void)? = nil  // For adding more goals (< 5)
    var onEditGoal: (() -> Void)? = nil
    var onChangeGoal: (() -> Void)? = nil
    var onAbandonGoal: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Section Header
            HStack {
                Text("Weekly Mission")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Spacer()

                // Goal count badge if has multiple goals
                if let data = missionData, data.goals.count > 1 {
                    Text("\(data.goals.count) Goals")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.systemPrimary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.systemPrimary.opacity(0.15))
                        .cornerRadius(50)
                }
            }
            .padding(.horizontal, 20)

            // Card Content based on state
            if let data = missionData {
                if data.needsGoalSetup {
                    EmptyMissionCard(onCreateGoal: onCreateGoal)
                } else if let mission = data.mission {
                    if mission.status == "offered" {
                        ReadyMissionCard(
                            mission: mission,
                            canAddMoreGoals: data.canAddMoreGoals,
                            onAccept: { onAcceptMission(mission.id) },
                            onAddGoal: onAddGoal,
                            onEditGoal: onEditGoal,
                            onChangeGoal: onChangeGoal,
                            onAbandonGoal: onAbandonGoal
                        )
                    } else {
                        ActiveMissionCard(
                            mission: mission,
                            goals: data.goals,
                            onViewDetails: {
                                onViewMission(mission.id)
                            }
                        )
                    }
                } else if data.hasActiveGoals {
                    // Has goal(s) but no mission yet (mid-week)
                    MidWeekCard(
                        goals: data.goals,
                        canAddMoreGoals: data.canAddMoreGoals,
                        onAddGoal: onAddGoal
                    )
                }
            } else if let error = missionLoadError {
                // Error state - show retry option
                ErrorMissionCard(error: error, onRetry: {
                    onRetry?()
                })
            } else {
                // Loading state
                LoadingMissionCard()
            }
        }
    }
}

// MARK: - Empty State (No Goals)

struct EmptyMissionCard: View {
    let onCreateGoal: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            // Icon
            ZStack {
                Circle()
                    .fill(Color.systemPrimary.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "target")
                    .font(.system(size: 36))
                    .foregroundColor(.systemPrimary)
            }

            // Text
            VStack(spacing: 8) {
                Text("No Active Goal")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)

                Text("Set a strength goal to receive personalized weekly training missions.")
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }

            // CTA Button
            Button(action: onCreateGoal) {
                HStack(spacing: 8) {
                    Image(systemName: "plus.circle.fill")
                    Text("Create Goal")
                }
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.black)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(Color.systemPrimary)
                .cornerRadius(50)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(Color.bgCard)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.systemPrimary.opacity(0.2), lineWidth: 1)
        )
        .padding(.horizontal, 20)
    }
}

// MARK: - Ready State (Mission Offered)

struct ReadyMissionCard: View {
    let mission: WeeklyMissionSummary
    let canAddMoreGoals: Bool
    let onAccept: () -> Void
    var onAddGoal: (() -> Void)? = nil
    var onEditGoal: (() -> Void)? = nil
    var onChangeGoal: (() -> Void)? = nil
    var onAbandonGoal: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Image(systemName: "bell.badge.fill")
                            .foregroundColor(.systemPrimary)
                        Text("Mission Ready")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.systemPrimary)
                    }

                    HStack(spacing: 8) {
                        Text("\(mission.workoutsTotal) workouts")
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)

                        if let split = mission.trainingSplit {
                            Text("•")
                                .foregroundColor(.textSecondary)
                            Text(formatTrainingSplit(split))
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(.systemPrimary)
                        }
                    }
                }

                Spacer()

                // XP Badge
                HStack(spacing: 4) {
                    Text("⚡️")
                    Text("+\(mission.xpReward)")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(.gold)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.gold.opacity(0.15))
                .cornerRadius(50)

                // Goal Management Menu
                Menu {
                    if canAddMoreGoals {
                        Button {
                            onAddGoal?()
                        } label: {
                            Label("Add Another Goal", systemImage: "plus.circle")
                        }

                        Divider()
                    }

                    Button {
                        onEditGoal?()
                    } label: {
                        Label("Edit Goals", systemImage: "pencil")
                    }

                    Button {
                        onChangeGoal?()
                    } label: {
                        Label("Change Goals", systemImage: "arrow.triangle.2.circlepath")
                    }

                    Divider()

                    Button(role: .destructive) {
                        onAbandonGoal?()
                    } label: {
                        Label("Abandon All Goals", systemImage: "xmark.circle")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.textSecondary)
                        .frame(width: 32, height: 32)
                }
            }

            // Goals summary (if multiple)
            if mission.goals.count > 1 {
                GoalsSummaryRow(goals: mission.goals)
            }

            // Workout Preview
            HStack(spacing: 8) {
                ForEach(mission.workouts, id: \.id) { workout in
                    MiniWorkoutBadge(
                        dayNumber: workout.dayNumber,
                        focus: workout.focus,
                        isCompleted: workout.status == "completed"
                    )
                }
            }

            // Accept Button
            Button(action: onAccept) {
                HStack {
                    Text("Accept Mission")
                    Image(systemName: "arrow.right")
                }
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    LinearGradient(
                        colors: [Color.systemPrimary, Color(hex: "00FF88")],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .cornerRadius(12)
            }
        }
        .padding(20)
        .background(Color.bgCard)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.systemPrimary.opacity(0.3), lineWidth: 1)
        )
        .shadow(color: Color.systemPrimary.opacity(0.1), radius: 20, y: 4)
        .padding(.horizontal, 20)
    }
}

// MARK: - Active State (Mission In Progress)

struct ActiveMissionCard: View {
    let mission: WeeklyMissionSummary
    let goals: [GoalSummaryResponse]
    let onViewDetails: () -> Void

    var progressPercent: Double {
        guard mission.workoutsTotal > 0 else { return 0 }
        return Double(mission.workoutsCompleted) / Double(mission.workoutsTotal)
    }

    var body: some View {
        Button(action: onViewDetails) {
            VStack(spacing: 16) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        // Show training split or primary goal name
                        if let split = mission.trainingSplit, goals.count > 1 {
                            Text(formatTrainingSplit(split))
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                        } else {
                            Text(mission.goalExerciseName)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                        }

                        HStack(spacing: 8) {
                            Text("\(mission.daysRemaining) days remaining")
                                .font(.system(size: 13))
                                .foregroundColor(.textSecondary)

                            if goals.count > 1 {
                                Text("•")
                                    .foregroundColor(.textSecondary)
                                Text("\(goals.count) goals")
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundColor(.systemPrimary)
                            }
                        }
                    }

                    Spacer()

                    // Progress Ring
                    ZStack {
                        Circle()
                            .stroke(Color.white.opacity(0.1), lineWidth: 4)
                            .frame(width: 44, height: 44)

                        Circle()
                            .trim(from: 0, to: progressPercent)
                            .stroke(Color.systemPrimary, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                            .frame(width: 44, height: 44)
                            .rotationEffect(.degrees(-90))

                        Text("\(mission.workoutsCompleted)/\(mission.workoutsTotal)")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }

                // Goals summary (if multiple)
                if goals.count > 1 {
                    GoalsSummaryRow(goals: goals)
                }

                // Workout Progress Bars
                HStack(spacing: 8) {
                    ForEach(mission.workouts, id: \.id) { workout in
                        MiniWorkoutBadge(
                            dayNumber: workout.dayNumber,
                            focus: workout.focus,
                            isCompleted: workout.status == "completed"
                        )
                    }
                }

                // View Details Button
                HStack {
                    Text("View Mission Details")
                        .font(.system(size: 14, weight: .medium))
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                }
                .foregroundColor(.systemPrimary)
            }
            .padding(20)
            .background(Color.bgCard)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.white.opacity(0.05), lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
        .padding(.horizontal, 20)
    }
}

// MARK: - Mid-Week Card (Goal(s) but no mission)

struct MidWeekCard: View {
    let goals: [GoalSummaryResponse]
    let canAddMoreGoals: Bool
    var onAddGoal: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    if goals.count == 1, let goal = goals.first {
                        Text("Goal: \(goal.exerciseName)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)

                        Text("\(Int(goal.targetWeight)) \(goal.weightUnit) target")
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)
                    } else if goals.count > 1 {
                        Text("\(goals.count) Active Goals")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)

                        Text(goals.map { $0.exerciseName }.joined(separator: ", "))
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Progress (average if multiple)
                if !goals.isEmpty {
                    let avgProgress = goals.reduce(0) { $0 + $1.progressPercent } / Double(goals.count)
                    CircularProgressView(progress: avgProgress / 100, size: 44)
                }
            }

            // Goals list (if multiple)
            if goals.count > 1 {
                GoalsSummaryRow(goals: goals)
            }

            // Info message and add button
            HStack(spacing: 8) {
                Image(systemName: "calendar")
                    .foregroundColor(.systemPrimary)
                Text("New mission available Sunday")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)

                Spacer()

                if canAddMoreGoals {
                    Button {
                        onAddGoal?()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "plus")
                                .font(.system(size: 12, weight: .semibold))
                            Text("Add Goal")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundColor(.systemPrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.systemPrimary.opacity(0.15))
                        .cornerRadius(50)
                    }
                }
            }
        }
        .padding(20)
        .background(Color.bgCard)
        .cornerRadius(16)
        .padding(.horizontal, 20)
    }
}

// MARK: - Goals Summary Row

struct GoalsSummaryRow: View {
    let goals: [GoalSummaryResponse]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(goals) { goal in
                    GoalChip(goal: goal)
                }
            }
        }
    }
}

struct GoalChip: View {
    let goal: GoalSummaryResponse

    var body: some View {
        HStack(spacing: 6) {
            Text(shortExerciseName(goal.exerciseName))
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white)

            Text("\(Int(goal.targetWeight))\(goal.weightUnit)")
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.systemPrimary)

            // Progress indicator
            Text("\(Int(goal.progressPercent))%")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.textSecondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.white.opacity(0.05))
        .cornerRadius(50)
        .overlay(
            RoundedRectangle(cornerRadius: 50)
                .stroke(Color.white.opacity(0.1), lineWidth: 1)
        )
    }

    private func shortExerciseName(_ name: String) -> String {
        // Shorten common exercise names
        let shortNames: [String: String] = [
            "Barbell Back Squat": "Squat",
            "Barbell Bench Press": "Bench",
            "Barbell Deadlift": "Deadlift",
            "Overhead Press": "OHP",
            "Barbell Row": "Row"
        ]
        return shortNames[name] ?? String(name.prefix(8))
    }
}

// MARK: - Loading State

struct LoadingMissionCard: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .tint(.systemPrimary)
            Text("Loading mission...")
                .font(.system(size: 14))
                .foregroundColor(.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(32)
        .background(Color.bgCard)
        .cornerRadius(16)
        .padding(.horizontal, 20)
    }
}

// MARK: - Error State

struct ErrorMissionCard: View {
    let error: String
    let onRetry: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            // Error icon
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 32))
                .foregroundColor(.systemOrange)

            // Error message
            VStack(spacing: 4) {
                Text("Failed to load mission")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)

                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }

            // Retry button
            Button(action: onRetry) {
                HStack(spacing: 6) {
                    Image(systemName: "arrow.clockwise")
                    Text("Retry")
                }
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.black)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(Color.systemPrimary)
                .cornerRadius(50)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(Color.bgCard)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.systemOrange.opacity(0.3), lineWidth: 1)
        )
        .padding(.horizontal, 20)
    }
}

// MARK: - Helper Components

struct MiniWorkoutBadge: View {
    let dayNumber: Int
    let focus: String
    let isCompleted: Bool

    var body: some View {
        VStack(spacing: 6) {
            // Day indicator
            Text("Day \(dayNumber)")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.textSecondary)

            // Focus/Status
            HStack(spacing: 4) {
                if isCompleted {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "00FF88"))
                } else {
                    Circle()
                        .fill(Color.white.opacity(0.2))
                        .frame(width: 8, height: 8)
                }

                Text(truncatedFocus)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(isCompleted ? Color(hex: "00FF88") : .white)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .padding(.horizontal, 8)
        .background(isCompleted ? Color(hex: "00FF88").opacity(0.1) : Color.white.opacity(0.03))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isCompleted ? Color(hex: "00FF88").opacity(0.3) : Color.white.opacity(0.05), lineWidth: 1)
        )
    }

    private var truncatedFocus: String {
        // Extract just the type (Push, Pull, Legs) from focus
        let words = focus.split(separator: " ")
        if let first = words.first {
            return String(first)
        }
        return focus
    }
}

struct CircularProgressView: View {
    let progress: Double
    let size: CGFloat

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.1), lineWidth: 4)
                .frame(width: size, height: size)

            Circle()
                .trim(from: 0, to: min(progress, 1.0))
                .stroke(Color.systemPrimary, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .frame(width: size, height: size)
                .rotationEffect(.degrees(-90))

            Text("\(Int(progress * 100))%")
                .font(.system(size: size * 0.22, weight: .semibold))
                .foregroundColor(.white)
        }
    }
}

#Preview {
    let sampleGoal = GoalSummaryResponse(
        id: "1",
        exerciseName: "Bench Press",
        targetWeight: 225,
        targetReps: 1,
        targetE1rm: 225,
        weightUnit: "lb",
        deadline: "2026-03-15",
        progressPercent: 82,
        status: "active"
    )

    let sampleWorkouts = [
        MissionWorkoutSummary(id: "w1", dayNumber: 1, focus: "Heavy Bench", status: "pending", exerciseCount: 4),
        MissionWorkoutSummary(id: "w2", dayNumber: 2, focus: "Pull", status: "pending", exerciseCount: 5),
        MissionWorkoutSummary(id: "w3", dayNumber: 3, focus: "Volume Bench", status: "pending", exerciseCount: 4)
    ]

    return ZStack {
        Color.bgVoid.ignoresSafeArea()

        ScrollView {
            VStack(spacing: 24) {
                // Empty state
                MissionCard(
                    missionData: CurrentMissionResponse(
                        hasActiveGoal: false,
                        hasActiveGoals: false,
                        goal: nil,
                        goals: [],
                        mission: nil,
                        needsGoalSetup: true,
                        canAddMoreGoals: true
                    ),
                    onCreateGoal: {},
                    onAcceptMission: { _ in },
                    onViewMission: { _ in }
                )

                // Ready state (single goal)
                MissionCard(
                    missionData: CurrentMissionResponse(
                        hasActiveGoal: true,
                        hasActiveGoals: true,
                        goal: sampleGoal,
                        goals: [sampleGoal],
                        mission: WeeklyMissionSummary(
                            id: "1",
                            goalExerciseName: "Bench Press",
                            goalTargetWeight: 225,
                            goalWeightUnit: "lb",
                            trainingSplit: nil,
                            goals: [sampleGoal],
                            goalCount: 1,
                            status: "offered",
                            weekStart: "2026-02-01",
                            weekEnd: "2026-02-07",
                            xpReward: 200,
                            workoutsCompleted: 0,
                            workoutsTotal: 3,
                            daysRemaining: 6,
                            workouts: sampleWorkouts
                        ),
                        needsGoalSetup: false,
                        canAddMoreGoals: true
                    ),
                    onCreateGoal: {},
                    onAcceptMission: { _ in },
                    onViewMission: { _ in }
                )
            }
            .padding(.vertical)
        }
    }
}

// MARK: - Shared Helpers

/// Formats training split identifier to display name
func formatTrainingSplit(_ split: String) -> String {
    switch split.lowercased() {
    case "ppl": return "Push/Pull/Legs"
    case "upper_lower": return "Upper/Lower"
    case "full_body": return "Full Body"
    case "single_focus": return "Focused Training"
    default: return split.capitalized
    }
}
