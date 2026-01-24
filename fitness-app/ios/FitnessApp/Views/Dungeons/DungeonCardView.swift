import SwiftUI

/// Compact dungeon card for list display
struct DungeonCardView: View {
    let dungeon: DungeonSummaryResponse
    var onTap: (() -> Void)? = nil

    /// Border color based on dungeon state
    private var borderColor: Color {
        if dungeon.isRareGate {
            return .gold
        } else if dungeon.isUrgent {
            return .warningRed.opacity(0.5)
        }
        return .ariseBorder
    }

    /// Border width - thicker for rare gates
    private var borderWidth: CGFloat {
        dungeon.isRareGate ? 2 : 1
    }

    var body: some View {
        Button {
            onTap?()
        } label: {
            HStack(spacing: 0) {
                // Rank indicator bar - golden for rare gates
                Rectangle()
                    .fill(dungeon.isRareGate ? Color.gold : dungeon.rankColor)
                    .frame(width: dungeon.isRareGate ? 6 : 4)

                HStack(spacing: 12) {
                    // Rank badge
                    DungeonRankBadge(rank: dungeon.rank, isRareGate: dungeon.isRareGate)

                    // Dungeon info
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(dungeon.name)
                                .font(.ariseHeader(size: 15, weight: .semibold))
                                .foregroundColor(.textPrimary)
                                .lineLimit(1)

                            if dungeon.isRareGate {
                                RareGateTag()
                            }

                            if dungeon.isBossDungeon {
                                BossTag()
                            }

                            if dungeon.isStretchDungeon {
                                StretchTag(percent: dungeon.stretchBonusPercent)
                            }
                        }

                        // Progress indicator
                        HStack(spacing: 8) {
                            // Objective progress
                            Text("\(dungeon.requiredObjectivesComplete)/\(dungeon.totalRequiredObjectives)")
                                .font(.ariseMono(size: 11))
                                .foregroundColor(dungeon.requiredObjectivesComplete >= dungeon.totalRequiredObjectives ? .successGreen : .textSecondary)

                            Text("objectives")
                                .font(.ariseMono(size: 10))
                                .foregroundColor(.textMuted)

                            Spacer()
                        }
                    }

                    Spacer()

                    // Right side: Time + XP
                    VStack(alignment: .trailing, spacing: 4) {
                        // Time remaining
                        TimeRemainingBadge(seconds: dungeon.timeRemainingSeconds, isUrgent: dungeon.isUrgent)

                        // XP reward
                        HStack(spacing: 4) {
                            Text("+\(dungeon.baseXpReward)")
                                .font(.ariseMono(size: 12, weight: .semibold))
                                .foregroundColor(.gold)
                            Text("XP")
                                .font(.ariseMono(size: 9))
                                .foregroundColor(.textMuted)
                        }
                    }

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.textMuted)
                }
                .padding(14)
            }
            .background(dungeon.isRareGate ? Color.gold.opacity(0.05) : Color.voidMedium)
            .cornerRadius(4)
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(borderColor, lineWidth: borderWidth)
            )
            .shadow(color: dungeon.isRareGate ? Color.gold.opacity(0.3) : .clear, radius: 8, x: 0, y: 0)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Dungeon Rank Badge

struct DungeonRankBadge: View {
    let rank: String
    var isRareGate: Bool = false

    var rankColor: Color {
        switch rank {
        case "E": return .rankE
        case "D": return .rankD
        case "C": return .rankC
        case "B": return .rankB
        case "A": return .rankA
        case "S", "S+", "S++": return .rankS
        default: return .textMuted
        }
    }

    var textColor: Color {
        switch rank {
        case "E", "D", "A": return .black
        case "C", "B", "S", "S+", "S++": return .white
        default: return .white
        }
    }

    var body: some View {
        Text(rank)
            .font(.ariseDisplay(size: 14, weight: .bold))
            .foregroundColor(textColor)
            .frame(width: 36, height: 36)
            .background(rankColor)
            .cornerRadius(4)
            .overlay(
                // Golden glow for rare gates
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.gold, lineWidth: isRareGate ? 2 : 0)
            )
            .shadow(color: isRareGate ? Color.gold.opacity(0.5) : .clear, radius: 6, x: 0, y: 0)
    }
}

// MARK: - Rare Gate Tag

struct RareGateTag: View {
    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "sparkles")
                .font(.system(size: 8))
            Text("RARE")
                .font(.ariseMono(size: 8, weight: .bold))
                .tracking(0.5)
        }
        .foregroundColor(.gold)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(Color.gold.opacity(0.2))
        .cornerRadius(2)
    }
}

// MARK: - Boss Tag

struct BossTag: View {
    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: "crown.fill")
                .font(.system(size: 8))
            Text("BOSS")
                .font(.ariseMono(size: 8, weight: .bold))
                .tracking(0.5)
        }
        .foregroundColor(.warningRed)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(Color.warningRed.opacity(0.15))
        .cornerRadius(2)
    }
}

// MARK: - Stretch Tag

struct StretchTag: View {
    var percent: Int?

    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: "arrow.up.right")
                .font(.system(size: 7, weight: .bold))
            Text("+\(percent ?? 50)%")
                .font(.ariseMono(size: 8, weight: .bold))
                .tracking(0.5)
        }
        .foregroundColor(.gold)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(Color.gold.opacity(0.15))
        .cornerRadius(2)
    }
}

// MARK: - Time Remaining Badge

struct TimeRemainingBadge: View {
    let seconds: Int
    var isUrgent: Bool = false

    var formattedTime: String {
        let hours = seconds / 3600
        if hours >= 24 {
            let days = hours / 24
            let remainingHours = hours % 24
            return "\(days)d \(remainingHours)h"
        }
        return "\(hours)h"
    }

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "clock.fill")
                .font(.system(size: 10))

            Text(formattedTime)
                .font(.ariseMono(size: 11, weight: .medium))
        }
        .foregroundColor(isUrgent ? .warningRed : .textSecondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(isUrgent ? Color.warningRed.opacity(0.1) : Color.voidLight)
        .cornerRadius(4)
    }
}

// MARK: - Preview

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 16) {
            // Sample dungeons would go here
            Text("Dungeon Card Preview")
                .foregroundColor(.textPrimary)
        }
        .padding()
    }
}
