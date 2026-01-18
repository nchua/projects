import SwiftUI

struct AchievementDetailSheet: View {
    let achievement: AchievementResponse
    @Environment(\.dismiss) private var dismiss

    var rarityColor: Color {
        switch achievement.rarity {
        case "legendary": return .gold
        case "epic": return .purple
        case "rare": return .systemPrimary
        default: return .textSecondary
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                ScrollView {
                    VStack(spacing: 24) {
                        // Achievement Icon with glow
                        ZStack {
                            // Outer glow
                            if achievement.unlocked {
                                Circle()
                                    .fill(rarityColor.opacity(0.2))
                                    .frame(width: 140, height: 140)
                                    .blur(radius: 20)
                            }

                            // Icon background
                            RoundedRectangle(cornerRadius: 16)
                                .fill(achievement.unlocked ? rarityColor.opacity(0.15) : Color.voidLight)
                                .frame(width: 100, height: 100)

                            // Icon
                            Image(systemName: achievement.icon)
                                .font(.system(size: 48))
                                .foregroundColor(achievement.unlocked ? rarityColor : .textMuted)
                                .opacity(achievement.unlocked ? 1 : 0.4)
                        }
                        .padding(.top, 24)

                        // Achievement Name
                        Text(achievement.name)
                            .font(.ariseHeader(size: 24, weight: .bold))
                            .foregroundColor(.textPrimary)
                            .multilineTextAlignment(.center)

                        // Rarity Badge
                        HStack(spacing: 8) {
                            RarityBadge(rarity: achievement.rarity, color: rarityColor)

                            Text("+\(achievement.xpReward) XP")
                                .font(.ariseMono(size: 12, weight: .semibold))
                                .foregroundColor(.systemPrimary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(Color.systemPrimary.opacity(0.1))
                                .cornerRadius(4)
                        }

                        // Description
                        Text(achievement.description)
                            .font(.ariseMono(size: 14))
                            .foregroundColor(.textSecondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)

                        // Category
                        HStack(spacing: 6) {
                            Image(systemName: "folder.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.textMuted)
                            Text(achievement.category.uppercased())
                                .font(.ariseMono(size: 11, weight: .medium))
                                .foregroundColor(.textMuted)
                                .tracking(0.5)
                        }
                        .padding(.top, 8)

                        // Unlock Status
                        VStack(spacing: 16) {
                            Divider()
                                .background(Color.ariseBorder)
                                .padding(.horizontal, 24)

                            if achievement.unlocked {
                                // Unlocked state
                                HStack(spacing: 12) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 24))
                                        .foregroundColor(.successGreen)

                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("ACHIEVEMENT UNLOCKED")
                                            .font(.ariseMono(size: 11, weight: .semibold))
                                            .foregroundColor(.successGreen)
                                            .tracking(1)

                                        if let unlockedAt = achievement.unlockedAt {
                                            Text(formatUnlockDate(unlockedAt))
                                                .font(.ariseMono(size: 12))
                                                .foregroundColor(.textSecondary)
                                        }
                                    }

                                    Spacer()
                                }
                                .padding(16)
                                .background(Color.successGreen.opacity(0.1))
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.successGreen.opacity(0.3), lineWidth: 1)
                                )
                                .padding(.horizontal, 24)
                            } else {
                                // Locked state with requirements
                                HStack(spacing: 12) {
                                    Image(systemName: "lock.fill")
                                        .font(.system(size: 24))
                                        .foregroundColor(.textMuted)

                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("LOCKED")
                                            .font(.ariseMono(size: 11, weight: .semibold))
                                            .foregroundColor(.textMuted)
                                            .tracking(1)

                                        Text(achievement.requirementDescription)
                                            .font(.ariseMono(size: 12))
                                            .foregroundColor(.textSecondary)
                                    }

                                    Spacer()
                                }
                                .padding(16)
                                .background(Color.voidLight)
                                .cornerRadius(4)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .stroke(Color.ariseBorder, lineWidth: 1)
                                )
                                .padding(.horizontal, 24)
                            }
                        }

                        Spacer(minLength: 40)
                    }
                }
            }
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

    private func formatUnlockDate(_ dateString: String) -> String {
        guard let date = dateString.parseISO8601Date() else {
            return dateString.formattedMonthDayFromISO
        }

        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM d, yyyy 'at' h:mm a"
        return formatter.string(from: date)
    }
}

// MARK: - Rarity Badge

struct RarityBadge: View {
    let rarity: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: rarityIcon)
                .font(.system(size: 10))
            Text(rarity.uppercased())
                .font(.ariseMono(size: 10, weight: .semibold))
                .tracking(0.5)
        }
        .foregroundColor(color)
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(color.opacity(0.1))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(color.opacity(0.3), lineWidth: 1)
        )
    }

    var rarityIcon: String {
        switch rarity {
        case "legendary": return "crown.fill"
        case "epic": return "star.fill"
        case "rare": return "sparkles"
        default: return "circle.fill"
        }
    }
}

#Preview {
    AchievementDetailSheet(achievement: AchievementResponse(
        id: "first_workout",
        name: "First Steps",
        description: "Complete your first workout and begin your journey",
        category: "milestones",
        icon: "figure.walk",
        xpReward: 100,
        rarity: "common",
        unlocked: true,
        unlockedAt: "2025-01-15T10:30:00Z"
    ))
}
