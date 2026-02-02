import SwiftUI

/// Mission card displayed on Home tab - shows current weekly mission status
/// Three states: empty (create goal), ready (accept mission), active (in progress)
struct MissionCard: View {
    let missionData: CurrentMissionResponse?
    let onCreateGoal: () -> Void
    let onAcceptMission: (String) -> Void
    let onViewMission: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Section Header
            Text("Weekly Mission")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.textPrimary)
                .padding(.horizontal, 20)

            // Card Content based on state
            if let data = missionData {
                if data.needsGoalSetup {
                    EmptyMissionCard(onCreateGoal: onCreateGoal)
                } else if let mission = data.mission {
                    if mission.status == "offered" {
                        ReadyMissionCard(mission: mission, onAccept: {
                            onAcceptMission(mission.id)
                        })
                    } else {
                        ActiveMissionCard(mission: mission, onViewDetails: {
                            onViewMission(mission.id)
                        })
                    }
                } else if data.hasActiveGoal {
                    // Has goal but no mission yet (mid-week)
                    MidWeekCard(goal: data.goal)
                }
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
    let onAccept: () -> Void

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

                    Text("\(mission.workoutsTotal) workouts this week")
                        .font(.system(size: 13))
                        .foregroundColor(.textSecondary)
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
                        Text(mission.goalExerciseName)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)

                        Text("\(mission.daysRemaining) days remaining")
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)
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

// MARK: - Mid-Week Card (Goal but no mission)

struct MidWeekCard: View {
    let goal: GoalSummaryResponse?

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    if let goal = goal {
                        Text("Goal: \(goal.exerciseName)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)

                        Text("\(Int(goal.targetWeight)) \(goal.weightUnit) target")
                            .font(.system(size: 13))
                            .foregroundColor(.textSecondary)
                    }
                }

                Spacer()

                // Progress
                if let goal = goal {
                    CircularProgressView(progress: goal.progressPercent / 100, size: 44)
                }
            }

            // Info message
            HStack(spacing: 8) {
                Image(systemName: "calendar")
                    .foregroundColor(.systemPrimary)
                Text("New mission available Sunday")
                    .font(.system(size: 13))
                    .foregroundColor(.textSecondary)
            }
        }
        .padding(20)
        .background(Color.bgCard)
        .cornerRadius(16)
        .padding(.horizontal, 20)
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
    ZStack {
        Color.bgVoid.ignoresSafeArea()

        ScrollView {
            VStack(spacing: 24) {
                // Empty state
                MissionCard(
                    missionData: CurrentMissionResponse(
                        hasActiveGoal: false,
                        goal: nil,
                        mission: nil,
                        needsGoalSetup: true
                    ),
                    onCreateGoal: {},
                    onAcceptMission: { _ in },
                    onViewMission: { _ in }
                )

                // Ready state
                MissionCard(
                    missionData: CurrentMissionResponse(
                        hasActiveGoal: true,
                        goal: GoalSummaryResponse(
                            id: "1",
                            exerciseName: "Bench Press",
                            targetWeight: 225,
                            weightUnit: "lb",
                            deadline: "2026-03-15",
                            progressPercent: 82,
                            status: "active"
                        ),
                        mission: WeeklyMissionSummary(
                            id: "1",
                            goalExerciseName: "Bench Press",
                            goalTargetWeight: 225,
                            goalWeightUnit: "lb",
                            status: "offered",
                            weekStart: "2026-02-01",
                            weekEnd: "2026-02-07",
                            xpReward: 200,
                            workoutsCompleted: 0,
                            workoutsTotal: 3,
                            daysRemaining: 6,
                            workouts: [
                                MissionWorkoutSummary(id: "w1", dayNumber: 1, focus: "Heavy Bench", status: "pending", exerciseCount: 4),
                                MissionWorkoutSummary(id: "w2", dayNumber: 2, focus: "Pull", status: "pending", exerciseCount: 5),
                                MissionWorkoutSummary(id: "w3", dayNumber: 3, focus: "Volume Bench", status: "pending", exerciseCount: 4)
                            ]
                        ),
                        needsGoalSetup: false
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
