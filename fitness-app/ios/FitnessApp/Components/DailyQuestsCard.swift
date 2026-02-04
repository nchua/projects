import SwiftUI

// MARK: - Edge Flow Daily Quests Section

struct DailyQuestsSection: View {
    let quests: [QuestResponse]
    let refreshAt: String?
    let onClaim: (String) -> Void
    var onViewWorkout: ((String) -> Void)? = nil  // Callback when tapping completed quest
    var onQuestTap: ((QuestResponse) -> Void)? = nil  // Callback when tapping any quest

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
                    EdgeFlowQuestRow(
                        quest: quest,
                        onClaim: onClaim,
                        onViewWorkout: onViewWorkout,
                        onTap: onQuestTap
                    )
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
    var onTap: ((QuestResponse) -> Void)? = nil   // Callback when tapping any quest (for detail sheet)

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
            // Call onTap to show detail sheet for any quest
            onTap?(quest)
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
        // All quests are tappable to show detail sheet
        .shadow(
            color: isClaimable ? Color(hex: "00FF88").opacity(0.1) : .clear,
            radius: 15,
            x: 0,
            y: 0
        )
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 24) {
            DailyQuestsSection(
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
                        completedByWorkoutId: "workout-123"
                    )
                ],
                refreshAt: ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600 * 8)),
                onClaim: { _ in }
            )
            .padding(.horizontal)
        }
    }
}
