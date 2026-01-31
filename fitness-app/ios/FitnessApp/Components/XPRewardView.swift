import SwiftUI

/// XP Reward popup shown after completing a workout
struct XPRewardView: View {
    let xpEarned: Int
    let xpBreakdown: [String: Int]
    let leveledUp: Bool
    let newLevel: Int?
    let rankChanged: Bool
    let newRank: String?
    let achievementsUnlocked: [AchievementUnlockedResponse]
    let onDismiss: () -> Void

    @State private var showContent = false
    @State private var xpCounterValue = 0
    @State private var showLevelUp = false
    @State private var showAchievements = false
    @State private var isDismissed = false

    var body: some View {
        ZStack {
            // Dark overlay
            Color.black.opacity(0.85)
                .ignoresSafeArea()
                .onTapGesture {
                    dismissSafely()
                }

            VStack(spacing: 24) {
                // Header
                VStack(spacing: 8) {
                    Text("QUEST COMPLETE")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .foregroundColor(.successGreen)
                        .tracking(2)
                        .opacity(showContent ? 1 : 0)
                        .animation(.easeOut(duration: 0.3).delay(0.2), value: showContent)

                    // XP Gained
                    HStack(alignment: .lastTextBaseline, spacing: 8) {
                        Text("+\(xpCounterValue)")
                            .font(.ariseDisplay(size: 56, weight: .bold))
                            .foregroundColor(.systemPrimary)
                            .shadow(color: .systemPrimaryGlow, radius: 20, x: 0, y: 0)

                        Text("XP")
                            .font(.ariseDisplay(size: 24, weight: .bold))
                            .foregroundColor(.systemPrimary.opacity(0.8))
                    }
                    .opacity(showContent ? 1 : 0)
                    .scaleEffect(showContent ? 1 : 0.5)
                    .animation(.spring(response: 0.5, dampingFraction: 0.7).delay(0.3), value: showContent)
                }

                // XP Breakdown
                if !xpBreakdown.isEmpty {
                    VStack(spacing: 8) {
                        ForEach(Array(xpBreakdown.keys.sorted()), id: \.self) { key in
                            if let value = xpBreakdown[key], value > 0 {
                                HStack {
                                    Text(formatBreakdownKey(key))
                                        .font(.ariseMono(size: 12))
                                        .foregroundColor(.textSecondary)

                                    Spacer()

                                    Text("+\(value)")
                                        .font(.ariseMono(size: 12, weight: .semibold))
                                        .foregroundColor(.systemPrimary)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 16)
                    .background(Color.voidMedium)
                    .cornerRadius(4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color.ariseBorder, lineWidth: 1)
                    )
                    .opacity(showContent ? 1 : 0)
                    .animation(.easeOut(duration: 0.3).delay(0.5), value: showContent)
                }

                // Level Up Animation
                if leveledUp, let level = newLevel {
                    VStack(spacing: 12) {
                        Text("LEVEL UP!")
                            .font(.ariseHeader(size: 20, weight: .bold))
                            .foregroundColor(.gold)
                            .shadow(color: .gold.opacity(0.5), radius: 10, x: 0, y: 0)

                        HStack(spacing: 8) {
                            Text("Level")
                                .font(.ariseMono(size: 14))
                                .foregroundColor(.textSecondary)

                            Text("\(level)")
                                .font(.ariseDisplay(size: 36, weight: .bold))
                                .foregroundColor(.gold)
                                .shadow(color: .gold.opacity(0.5), radius: 15, x: 0, y: 0)
                        }

                        if rankChanged, let rank = newRank {
                            HStack(spacing: 8) {
                                Text("NEW RANK:")
                                    .font(.ariseMono(size: 11))
                                    .foregroundColor(.textMuted)

                                RankBadgeView(rank: HunterRank(rawValue: rank) ?? .e, size: .medium)

                                Text("\(rank)-RANK HUNTER")
                                    .font(.ariseHeader(size: 14, weight: .bold))
                                    .foregroundColor(.systemPrimary)
                            }
                        }
                    }
                    .padding(.vertical, 16)
                    .padding(.horizontal, 32)
                    .background(Color.gold.opacity(0.1))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.gold.opacity(0.3), lineWidth: 1)
                    )
                    .opacity(showLevelUp ? 1 : 0)
                    .scaleEffect(showLevelUp ? 1 : 0.8)
                    .animation(.spring(response: 0.5, dampingFraction: 0.7), value: showLevelUp)
                }

                // Achievements Unlocked
                if !achievementsUnlocked.isEmpty {
                    VStack(spacing: 12) {
                        Text("ACHIEVEMENTS UNLOCKED")
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(.gold)
                            .tracking(1)

                        ForEach(achievementsUnlocked) { achievement in
                            AchievementUnlockedCard(achievement: achievement)
                        }
                    }
                    .opacity(showAchievements ? 1 : 0)
                    .animation(.easeOut(duration: 0.3), value: showAchievements)
                }

                // Continue Button
                Button {
                    dismissSafely()
                } label: {
                    Text("CONTINUE")
                        .font(.ariseHeader(size: 16, weight: .bold))
                        .tracking(2)
                        .foregroundColor(.voidBlack)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.systemPrimary)
                        .cornerRadius(4)
                }
                .opacity(showContent ? 1 : 0)
                .animation(.easeOut(duration: 0.3).delay(0.8), value: showContent)
            }
            .padding(24)
        }
        .onAppear {
            startAnimations()
        }
    }

    private func startAnimations() {
        // Start showing content
        withAnimation {
            showContent = true
        }

        // Animate XP counter
        let duration: Double = 1.0
        let steps = 30
        let stepValue = xpEarned / steps
        let stepDuration = duration / Double(steps)

        for i in 0..<steps {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5 + (stepDuration * Double(i))) {
                xpCounterValue = min((i + 1) * stepValue, xpEarned)
            }
        }
        // Ensure final value is exact
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5 + duration) {
            xpCounterValue = xpEarned
        }

        // Show level up after XP counter
        if leveledUp {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
                showLevelUp = true
            }
        }

        // Show achievements
        if !achievementsUnlocked.isEmpty {
            let delay = leveledUp ? 2.5 : 1.8
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                showAchievements = true
            }
        }
    }

    private func dismissSafely() {
        // Prevent double dismissal from rapid taps
        guard !isDismissed else { return }
        isDismissed = true
        onDismiss()
    }

    private func formatBreakdownKey(_ key: String) -> String {
        switch key {
        case "workout_complete": return "Workout Completed"
        case "volume_bonus": return "Volume Bonus"
        case "big_three_bonus": return "Big Three Bonus"
        case "pr_bonus": return "PR Achieved"
        case "streak_bonus": return "Streak Bonus"
        default: return key.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

struct AchievementUnlockedCard: View {
    let achievement: AchievementUnlockedResponse

    var rarityColor: Color {
        switch achievement.rarity {
        case "legendary": return .gold
        case "epic": return .purple
        case "rare": return .systemPrimary
        default: return .textSecondary
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            ZStack {
                Circle()
                    .fill(rarityColor.opacity(0.2))
                    .frame(width: 44, height: 44)

                Image(systemName: achievement.icon)
                    .font(.system(size: 20))
                    .foregroundColor(rarityColor)
            }

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text(achievement.name)
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text(achievement.description)
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textSecondary)
                    .lineLimit(1)
            }

            Spacer()

            // XP Reward
            VStack(alignment: .trailing, spacing: 2) {
                Text("+\(achievement.xpReward)")
                    .font(.ariseMono(size: 14, weight: .bold))
                    .foregroundColor(.systemPrimary)

                Text("XP")
                    .font(.ariseMono(size: 9))
                    .foregroundColor(.textMuted)
            }
        }
        .padding(12)
        .background(rarityColor.opacity(0.05))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(rarityColor.opacity(0.3), lineWidth: 1)
        )
    }
}

#Preview {
    XPRewardView(
        xpEarned: 185,
        xpBreakdown: [
            "workout_complete": 50,
            "volume_bonus": 35,
            "big_three_bonus": 45,
            "pr_bonus": 100
        ],
        leveledUp: true,
        newLevel: 8,
        rankChanged: false,
        newRank: nil,
        achievementsUnlocked: [
            AchievementUnlockedResponse(
                id: "bench_225",
                name: "Bench Baron",
                description: "Bench press 225 lbs",
                icon: "dumbbell.fill",
                xpReward: 250,
                rarity: "epic"
            )
        ],
        onDismiss: {}
    )
}
