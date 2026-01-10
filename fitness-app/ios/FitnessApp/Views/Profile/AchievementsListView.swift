import SwiftUI

struct AchievementsListView: View {
    let achievements: [AchievementResponse]
    @Environment(\.dismiss) private var dismiss

    var unlockedCount: Int {
        achievements.filter { $0.unlocked }.count
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                if achievements.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "trophy")
                            .font(.system(size: 48))
                            .foregroundColor(.textMuted)

                        Text("No achievements available")
                            .font(.ariseHeader(size: 16, weight: .medium))
                            .foregroundColor(.textSecondary)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 16) {
                            // Stats header
                            HStack(spacing: 24) {
                                VStack(spacing: 4) {
                                    Text("\(unlockedCount)")
                                        .font(.ariseDisplay(size: 28, weight: .bold))
                                        .foregroundColor(.gold)

                                    Text("UNLOCKED")
                                        .font(.ariseMono(size: 10, weight: .semibold))
                                        .foregroundColor(.textMuted)
                                        .tracking(1)
                                }

                                VStack(spacing: 4) {
                                    Text("\(achievements.count)")
                                        .font(.ariseDisplay(size: 28, weight: .bold))
                                        .foregroundColor(.systemPrimary)

                                    Text("TOTAL")
                                        .font(.ariseMono(size: 10, weight: .semibold))
                                        .foregroundColor(.textMuted)
                                        .tracking(1)
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 20)
                            .background(Color.voidMedium)
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                            .padding(.horizontal)

                            // Achievement list
                            LazyVStack(spacing: 12) {
                                ForEach(achievements) { achievement in
                                    AchievementRowView(achievement: achievement)
                                }
                            }
                            .padding(.horizontal)

                            Spacer(minLength: 20)
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationTitle("Achievements")
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
    }
}

// MARK: - Achievement Row View

struct AchievementRowView: View {
    let achievement: AchievementResponse

    var rarityColor: Color {
        switch achievement.rarity {
        case "legendary": return .gold
        case "epic": return .purple
        case "rare": return .systemPrimary
        default: return .textSecondary
        }
    }

    var body: some View {
        HStack(spacing: 16) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(achievement.unlocked ? rarityColor.opacity(0.15) : Color.voidLight)
                    .frame(width: 56, height: 56)

                Image(systemName: achievement.icon)
                    .font(.system(size: 24))
                    .foregroundColor(achievement.unlocked ? rarityColor : .textMuted)
                    .opacity(achievement.unlocked ? 1 : 0.4)
            }

            // Info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(achievement.name)
                        .font(.ariseHeader(size: 15, weight: .semibold))
                        .foregroundColor(achievement.unlocked ? .textPrimary : .textMuted)

                    if achievement.unlocked {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundColor(.successGreen)
                    }
                }

                Text(achievement.description)
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textSecondary)
                    .lineLimit(2)

                HStack(spacing: 12) {
                    // Rarity badge
                    Text(achievement.rarity.uppercased())
                        .font(.ariseMono(size: 9, weight: .semibold))
                        .foregroundColor(rarityColor)
                        .tracking(0.5)

                    // XP reward
                    HStack(spacing: 4) {
                        Text("+\(achievement.xpReward)")
                            .font(.ariseMono(size: 10, weight: .medium))
                            .foregroundColor(.systemPrimary)
                        Text("XP")
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }

                    // Unlock date if available
                    if let unlockedAt = achievement.unlockedAt {
                        Text(formatDate(unlockedAt))
                            .font(.ariseMono(size: 9))
                            .foregroundColor(.textMuted)
                    }
                }
            }

            Spacer()
        }
        .padding(12)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(achievement.unlocked ? rarityColor.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
        )
        .opacity(achievement.unlocked ? 1 : 0.7)
    }

    private func formatDate(_ dateString: String) -> String {
        dateString.formattedMonthDayFromISO
    }
}

#Preview {
    AchievementsListView(achievements: [])
}
