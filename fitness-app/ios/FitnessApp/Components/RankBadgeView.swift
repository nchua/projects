import SwiftUI

/// ARISE rank badge (E through S) with color coding
struct RankBadgeView: View {
    let rank: HunterRank
    var size: BadgeSize = .medium

    enum BadgeSize {
        case small, medium, large

        var fontSize: CGFloat {
            switch self {
            case .small: return 12
            case .medium: return 14
            case .large: return 18
            }
        }

        var horizontalPadding: CGFloat {
            switch self {
            case .small: return 8
            case .medium: return 12
            case .large: return 16
            }
        }

        var verticalPadding: CGFloat {
            switch self {
            case .small: return 2
            case .medium: return 4
            case .large: return 6
            }
        }
    }

    var body: some View {
        Text(rank.rawValue)
            .font(.ariseDisplay(size: size.fontSize, weight: .bold))
            .tracking(1)
            .padding(.horizontal, size.horizontalPadding)
            .padding(.vertical, size.verticalPadding)
            .background(rank.color)
            .foregroundColor(rank.textColor)
            .cornerRadius(2)
    }
}

/// Hunter avatar with rank badge overlay
struct HunterAvatarView: View {
    let initial: String
    let rank: HunterRank
    var size: CGFloat = 70

    var body: some View {
        ZStack {
            // Avatar background with gradient
            RoundedRectangle(cornerRadius: 4)
                .fill(
                    LinearGradient(
                        colors: [.voidLight, .voidMedium],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size, height: size)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(rank.color.opacity(0.5), lineWidth: 2)
                )

            // Initial letter
            Text(initial.uppercased())
                .font(.ariseDisplay(size: size * 0.4, weight: .bold))
                .foregroundColor(.textPrimary)
        }
        .overlay(alignment: .bottomTrailing) {
            RankBadgeView(rank: rank, size: .small)
                .offset(x: 8, y: 8)
        }
    }
}

/// Level display with glow effect
struct LevelDisplayView: View {
    let level: Int
    var showGlow: Bool = true

    var body: some View {
        VStack(spacing: 2) {
            Text("\(level)")
                .font(.ariseDisplay(size: 32, weight: .bold))
                .foregroundColor(.systemPrimary)
                .if(showGlow) { view in
                    view.shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)
                }

            Text("LEVEL")
                .font(.ariseMono(size: 10, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(1)
        }
    }
}

/// Hunter title display
struct HunterTitleView: View {
    let name: String
    let title: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(name)
                .font(.ariseHeader(size: 24, weight: .bold))
                .foregroundColor(.textPrimary)

            Text("\"\(title)\"")
                .font(.ariseMono(size: 12, weight: .regular))
                .foregroundColor(.textMuted)
                .italic()
        }
    }
}

/// Complete hunter header (avatar + info + level)
struct HunterHeaderView: View {
    let name: String
    let rank: HunterRank
    let level: Int
    var initial: String? = nil

    var displayInitial: String {
        initial ?? String(name.prefix(1))
    }

    var body: some View {
        HStack(spacing: 16) {
            HunterAvatarView(initial: displayInitial, rank: rank)

            HunterTitleView(name: name, title: rank.title)

            Spacer()

            LevelDisplayView(level: level)
        }
    }
}

/// Streak display with flame icon
struct StreakDisplayView: View {
    let days: Int

    var body: some View {
        HStack(spacing: 4) {
            Text("\u{1F525}") // Fire emoji
                .font(.system(size: 16))

            Text("\(days)")
                .font(.ariseDisplay(size: 20, weight: .bold))
                .foregroundColor(.gold)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.gold.opacity(0.05))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.gold.opacity(0.2), lineWidth: 1)
        )
    }
}

#Preview {
    ZStack {
        VoidBackground()

        VStack(spacing: 32) {
            // Rank badges
            HStack(spacing: 16) {
                ForEach(HunterRank.allCases, id: \.self) { rank in
                    RankBadgeView(rank: rank)
                }
            }

            // Hunter header
            HunterHeaderView(name: "Nick", rank: .e, level: 7)
                .padding()
                .systemPanelStyle()

            // Avatar examples
            HStack(spacing: 24) {
                HunterAvatarView(initial: "N", rank: .e)
                HunterAvatarView(initial: "A", rank: .a)
                HunterAvatarView(initial: "S", rank: .s)
            }

            // Streak
            StreakDisplayView(days: 12)
        }
        .padding()
    }
}
