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
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(rank.rawValue) rank")
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
                .scaleEffect(0.85)
                .offset(x: 2, y: 2)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Hunter avatar, \(rank.rawValue) rank")
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

            // Avatar examples
            HStack(spacing: 24) {
                HunterAvatarView(initial: "N", rank: .e)
                HunterAvatarView(initial: "A", rank: .a)
                HunterAvatarView(initial: "S", rank: .s)
            }
        }
        .padding()
    }
}
