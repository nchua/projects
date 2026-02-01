import SwiftUI

// MARK: - Edge Flow Daily Quests Section

struct DailyQuestsSection: View {
    let quests: [QuestResponse]
    let refreshAt: String?
    let onClaim: (String) -> Void
    var onViewWorkout: ((String) -> Void)? = nil  // Callback when tapping completed quest

    var completedCount: Int {
        quests.filter { $0.isClaimed }.count
    }

    var completedCount: Int {
        quests.filter { $0.isCompleted }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Header with completion counter
            HStack {
                Text("Daily Quests")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Spacer()

                // Completion badge
                if completedCount > 0 {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 12))
                        Text("\(completedCount)/\(quests.count)")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(completedCount == quests.count ? Color(hex: "00FF88") : .textMuted)
                }
            }

            // Quest List
            VStack(spacing: 10) {
                ForEach(quests) { quest in
                    EdgeFlowQuestRow(quest: quest, onClaim: onClaim, onViewWorkout: onViewWorkout)
                }
            }

            // All complete message - only show when there are quests and all are completed
            if !quests.isEmpty && completedCount == quests.count {
                Text("All quests completed! 🎉")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.successGreen)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)
            }
        }
        .padding(.horizontal, 20)
    }
}

struct EdgeFlowQuestRow: View {
    let quest: QuestResponse
    let onClaim: (String) -> Void
    var onViewWorkout: ((String) -> Void)? = nil  // Callback when tapping completed quest

    var isClaimable: Bool {
        quest.isCompleted && !quest.isClaimed
    }

    /// Can navigate to workout if quest is claimed and has a workout ID
    var canNavigateToWorkout: Bool {
        quest.isClaimed && quest.completedByWorkoutId != nil
    }

    var accentColor: Color {
        if quest.isClaimed {
            return Color(hex: "00FF88").opacity(0.5)  // Dimmed green for claimed
        } else if isClaimable {
            return Color(hex: "00FF88")  // Bright green for claimable
        } else {
            return Color.white.opacity(0.1)  // Default for in-progress
        }
    }

    var questIcon: String {
        if quest.isClaimed {
            return "\u{2705}"  // White checkmark in green box
        }
        switch quest.questType {
        case "total_reps": return "\u{1F4AA}"      // Flexed bicep
        case "compound_sets": return "\u{1F3AF}"  // Target
        case "total_volume": return "\u{1F4C8}"   // Chart
        case "training_time": return "\u{23F1}"   // Stopwatch
        default: return "\u{1F4AA}"
        }
    }

    var body: some View {
        Button {
            // Navigate to workout if claimed and has workout ID
            if let workoutId = quest.completedByWorkoutId, canNavigateToWorkout {
                onViewWorkout?(workoutId)
            }
        } label: {
            HStack(spacing: 12) {
                // Quest Icon
                Text(questIcon)
                    .font(.system(size: 18))

                // Quest Info
                VStack(alignment: .leading, spacing: 2) {
                    Text(quest.name)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(quest.isClaimed ? .textMuted : .textPrimary)
                        .strikethrough(quest.isClaimed, color: .textMuted)

                    if quest.isClaimed {
                        HStack(spacing: 4) {
                            Text("Completed!")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "00FF88").opacity(0.7))
                            if canNavigateToWorkout {
                                Text("• View workout")
                                    .font(.system(size: 12))
                                    .foregroundColor(.textMuted)
                            }
                        }
                    } else {
                        Text(isClaimable ? "Ready to claim!" : "\(quest.progress)/\(quest.targetValue)")
                            .font(.system(size: 12))
                            .foregroundColor(isClaimable ? Color(hex: "00FF88") : .textMuted)
                    }
                }

                Spacer()

                // XP or Claim Button
                if isClaimable {
                    Button {
                        onClaim(quest.id)
                    } label: {
                        Text("Claim")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.black)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6)
                            .background(Color(hex: "00FF88"))
                            .clipShape(Capsule())
                            .shadow(color: Color(hex: "00FF88").opacity(0.3), radius: 10, x: 0, y: 0)
                    }
                } else if quest.isClaimed {
                    // Show earned XP with chevron for navigation
                    HStack(spacing: 6) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 12))
                            Text("+\(quest.xpReward)")
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundColor(Color(hex: "00FF88").opacity(0.6))

                        if canNavigateToWorkout {
                            Image(systemName: "chevron.right")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(.textMuted)
                        }
                    }
                } else {
                    Text("+\(quest.xpReward) XP")
                        .font(.system(size: 12))
                        .foregroundColor(.textMuted)
                }
            }
            .padding(14)
            .background(quest.isClaimed ? Color.voidMedium.opacity(0.6) : Color.voidMedium)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                // Left accent bar
                HStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(accentColor)
                        .frame(width: 3)
                    Spacer()
                }
            )
        }
        .buttonStyle(.plain)
        .disabled(!canNavigateToWorkout && !isClaimable)
        .shadow(
            color: isClaimable ? Color(hex: "00FF88").opacity(0.1) : .clear,
            radius: 15,
            x: 0,
            y: 0
        )
    }
}

// MARK: - Legacy Daily Quests Card (kept for compatibility)

/// Compact daily quests card - minimal space usage
struct DailyQuestsCard: View {
    let quests: [QuestResponse]
    let refreshAt: String
    let onClaim: (String) -> Void

    var completedCount: Int {
        quests.filter { $0.isCompleted }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("[ DAILY QUESTS ]")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textMuted)
                    .tracking(1)

                Spacer()

                Text("\(completedCount)/\(quests.count) completed")
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textSecondary)
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 12)

            // Divider
            Rectangle()
                .fill(Color.ariseBorder)
                .frame(height: 1)

            // Quest rows - no spacing, dividers between
            VStack(spacing: 0) {
                ForEach(Array(quests.enumerated()), id: \.element.id) { index, quest in
                    CompactQuestRow(quest: quest, onClaim: onClaim)

                    if index < quests.count - 1 {
                        Rectangle()
                            .fill(Color.ariseBorder.opacity(0.5))
                            .frame(height: 1)
                            .padding(.leading, 44)
                    }
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

/// Compact quest row - tap to expand details
struct CompactQuestRow: View {
    let quest: QuestResponse
    let onClaim: (String) -> Void

    @State private var isExpanded = false

    var progressPercent: Double {
        guard quest.targetValue > 0 else { return 0 }
        return min(1.0, Double(quest.progress) / Double(quest.targetValue))
    }

    /// Show progress bar only for incomplete quests with partial progress
    var showProgressBar: Bool {
        !quest.isCompleted && quest.progress > 0 && quest.progress < quest.targetValue
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Main row - always visible
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: 12) {
                    // Status checkbox (tap to claim if ready)
                    Button {
                        if quest.isCompleted && !quest.isClaimed {
                            onClaim(quest.id)
                        }
                    } label: {
                        QuestCheckbox(
                            isCompleted: quest.isCompleted,
                            isClaimed: quest.isClaimed,
                            isClaimable: quest.isCompleted && !quest.isClaimed
                        )
                    }
                    .buttonStyle(.plain)

                    // Quest name and progress bar
                    VStack(alignment: .leading, spacing: 4) {
                        Text(quest.name)
                            .font(.ariseBody(size: 14))
                            .foregroundColor(quest.isClaimed ? .textMuted : .textPrimary)
                            .lineLimit(1)

                        // Progress bar - only show for partial progress
                        if showProgressBar {
                            GeometryReader { geometry in
                                ZStack(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(Color.voidLight)
                                        .frame(height: 4)

                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(Color.systemPrimary)
                                        .frame(width: geometry.size.width * progressPercent, height: 4)
                                }
                            }
                            .frame(height: 4)
                        }
                    }

                    Spacer()

                    // XP Reward
                    Text("+\(quest.xpReward) XP")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .foregroundColor(quest.isClaimed ? .textMuted : .gold)

                    // Expand indicator
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // Expanded details
            if isExpanded {
                VStack(alignment: .leading, spacing: 8) {
                    // Description
                    Text(quest.description)
                        .font(.ariseMono(size: 12))
                        .foregroundColor(.textSecondary)

                    // Progress detail
                    HStack {
                        Text("Progress:")
                            .font(.ariseMono(size: 11))
                            .foregroundColor(.textMuted)

                        Text("\(quest.progress)/\(quest.targetValue)")
                            .font(.ariseMono(size: 11, weight: .semibold))
                            .foregroundColor(quest.isCompleted ? .successGreen : .textPrimary)

                        Spacer()

                        // Claim button if ready
                        if quest.isCompleted && !quest.isClaimed {
                            Button {
                                onClaim(quest.id)
                            } label: {
                                Text("CLAIM")
                                    .font(.ariseMono(size: 10, weight: .bold))
                                    .tracking(1)
                                    .foregroundColor(.voidBlack)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(Color.gold)
                                    .cornerRadius(2)
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.leading, 36) // Align with quest name
                .padding(.bottom, 12)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }
}

/// Checkbox indicator for quest status
struct QuestCheckbox: View {
    let isCompleted: Bool
    let isClaimed: Bool
    let isClaimable: Bool

    var body: some View {
        ZStack {
            if isClaimed {
                // Claimed - filled green with checkmark
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.successGreen)
                    .frame(width: 24, height: 24)

                Image(systemName: "checkmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.voidBlack)
            } else if isClaimable {
                // Ready to claim - filled green with ellipsis (tap to claim)
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.successGreen)
                    .frame(width: 24, height: 24)

                Text("...")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.voidBlack)
                    .offset(y: -2)
            } else {
                // Incomplete - empty box
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.textMuted.opacity(0.5), lineWidth: 1.5)
                    .frame(width: 24, height: 24)
            }
        }
    }
}

/// Countdown timer showing time until refresh
struct RefreshTimerView: View {
    let refreshAt: String

    @State private var timeRemaining: String = "..."

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "clock")
                .font(.system(size: 10))
                .foregroundColor(.textMuted)

            Text(timeRemaining)
                .font(.ariseMono(size: 10))
                .foregroundColor(.textMuted)
        }
        .onAppear {
            updateTimer()
        }
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { _ in
            updateTimer()
        }
    }

    private func updateTimer() {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        // Try with fractional seconds first, then without
        var refreshDate = formatter.date(from: refreshAt)
        if refreshDate == nil {
            formatter.formatOptions = [.withInternetDateTime]
            refreshDate = formatter.date(from: refreshAt)
        }

        guard let targetDate = refreshDate else {
            timeRemaining = "--:--"
            return
        }

        let now = Date()
        let interval = targetDate.timeIntervalSince(now)

        if interval <= 0 {
            timeRemaining = "Now!"
            return
        }

        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60

        if hours > 0 {
            timeRemaining = "\(hours)h \(minutes)m"
        } else {
            timeRemaining = "\(minutes)m"
        }
    }
}

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 24) {
            DailyQuestsCard(
                quests: [
                    QuestResponse(
                        id: "1",
                        questId: "reps_100",
                        name: "Century Club",
                        description: "Complete 100 total reps",
                        questType: "total_reps",
                        targetValue: 100,
                        xpReward: 25,
                        progress: 75,
                        isCompleted: false,
                        isClaimed: false,
                        difficulty: "normal",
                        completedByWorkoutId: nil
                    ),
                    QuestResponse(
                        id: "2",
                        questId: "compound_5",
                        name: "Compound Focus",
                        description: "Do 5 sets of compound lifts",
                        questType: "compound_sets",
                        targetValue: 5,
                        xpReward: 30,
                        progress: 5,
                        isCompleted: true,
                        isClaimed: false,
                        difficulty: "normal",
                        completedByWorkoutId: nil
                    ),
                    QuestResponse(
                        id: "3",
                        questId: "volume_5k",
                        name: "Volume Builder",
                        description: "Lift 5,000 lbs total",
                        questType: "total_volume",
                        targetValue: 5000,
                        xpReward: 25,
                        progress: 5000,
                        isCompleted: true,
                        isClaimed: true,
                        difficulty: "easy",
                        completedByWorkoutId: "workout-123"  // Has workout ID for navigation
                    )
                ],
                refreshAt: ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600 * 8)),
                onClaim: { _ in }
            )
            .padding(.horizontal)
        }
    }
}
