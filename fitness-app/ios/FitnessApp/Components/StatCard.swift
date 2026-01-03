import SwiftUI

/// ARISE stat card with icon, value, and label
struct StatCard: View {
    let icon: String  // Emoji or SF Symbol name
    let value: String
    let label: String
    var useSystemIcon: Bool = false
    var valueColor: Color = .systemPrimary
    var showGlow: Bool = true

    var body: some View {
        VStack(spacing: 8) {
            // Icon
            if useSystemIcon {
                Image(systemName: icon)
                    .font(.system(size: 20))
                    .foregroundColor(.textSecondary)
            } else {
                Text(icon)
                    .font(.system(size: 20))
            }

            // Value
            Text(value)
                .font(.ariseDisplay(size: 24, weight: .bold))
                .foregroundColor(valueColor)
                .if(showGlow) { view in
                    view.shadow(color: valueColor.opacity(0.4), radius: 10, x: 0, y: 0)
                }

            // Label
            Text(label)
                .font(.ariseMono(size: 10, weight: .medium))
                .foregroundColor(.textMuted)
                .textCase(.uppercase)
                .tracking(0.5)
        }
        .frame(maxWidth: .infinity)
        .padding(16)
        .background(Color.systemPrimarySubtle.opacity(0.2))
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.systemPrimarySubtle, lineWidth: 1)
        )
    }
}

/// Grid of stats (3 columns by default)
struct StatGridView: View {
    let stats: [StatItem]
    var columns: Int = 3

    struct StatItem: Identifiable {
        let id = UUID()
        let icon: String
        let value: String
        let label: String
        var useSystemIcon: Bool = false
        var valueColor: Color = .systemPrimary
    }

    var gridColumns: [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: 12), count: columns)
    }

    var body: some View {
        LazyVGrid(columns: gridColumns, spacing: 12) {
            ForEach(Array(stats.enumerated()), id: \.element.id) { index, stat in
                StatCard(
                    icon: stat.icon,
                    value: stat.value,
                    label: stat.label,
                    useSystemIcon: stat.useSystemIcon,
                    valueColor: stat.valueColor
                )
                .fadeIn(delay: Double(index) * 0.1)
            }
        }
    }
}

/// ARISE lift card with fantasy name and stats
struct LiftStatCard: View {
    let name: String
    let e1rm: Double
    let bodyweightMultiplier: Double
    var rank: HunterRank? = nil

    var fantasyName: String {
        ExerciseFantasyNames.fantasyName(for: name)
    }

    var liftColor: Color {
        Color.exerciseColor(for: name)
    }

    var body: some View {
        HStack {
            // Left border indicator
            Rectangle()
                .fill(liftColor)
                .frame(width: 3)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(name)
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    if let rank = rank {
                        RankBadgeView(rank: rank, size: .small)
                    }
                }

                Text("\"\(fantasyName)\"")
                    .font(.ariseMono(size: 12, weight: .regular))
                    .foregroundColor(.textMuted)
                    .italic()
            }
            .padding(.leading, 12)

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                HStack(alignment: .lastTextBaseline, spacing: 4) {
                    Text("\(Int(e1rm))")
                        .font(.ariseDisplay(size: 24, weight: .bold))
                        .foregroundColor(.textPrimary)

                    Text("lb")
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.textMuted)
                }

                Text("\(bodyweightMultiplier, specifier: "%.2f")x BW")
                    .font(.ariseMono(size: 12, weight: .medium))
                    .foregroundColor(liftColor)
            }
        }
        .padding(.vertical, 16)
        .padding(.trailing, 16)
        .background(Color.black.opacity(0.3))
    }
}

/// Currency display (gold/points)
struct CurrencyDisplayView: View {
    let gold: Int
    let points: Int

    var body: some View {
        HStack(spacing: 24) {
            // Gold
            HStack(spacing: 6) {
                Text("\u{1FA99}") // Coin emoji
                    .font(.system(size: 16))

                Text("\(gold)")
                    .font(.ariseDisplay(size: 16, weight: .bold))
                    .foregroundColor(.gold)
            }

            // Points
            HStack(spacing: 6) {
                Text("\u{2B50}") // Star emoji
                    .font(.system(size: 16))

                Text("\(points)")
                    .font(.ariseDisplay(size: 16, weight: .bold))
                    .foregroundColor(.systemPrimary)
            }
        }
    }
}

/// Accessory quest card (completed/pending state)
struct AccessoryCard: View {
    let name: String
    let isCompleted: Bool

    var body: some View {
        VStack(spacing: 8) {
            if isCompleted {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 24))
                    .foregroundColor(.successGreen)
            } else {
                Circle()
                    .stroke(Color.textMuted, lineWidth: 1)
                    .frame(width: 24, height: 24)
            }

            Text(name)
                .font(.ariseMono(size: 11, weight: .medium))
                .foregroundColor(isCompleted ? .textPrimary : .textMuted)
                .textCase(.uppercase)
                .tracking(0.5)
                .multilineTextAlignment(.center)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .padding(.horizontal, 10)
        .background(
            isCompleted
            ? Color.successGreen.opacity(0.05)
            : Color.black.opacity(0.3)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(
                    isCompleted ? Color.successGreen.opacity(0.3) : Color.ariseBorderLight,
                    lineWidth: 1
                )
        )
    }
}

#Preview {
    ZStack {
        VoidBackground()

        ScrollView {
            VStack(spacing: 24) {
                // Stat grid
                AriseSectionHeader(title: "Hunter Stats")

                StatGridView(stats: [
                    .init(icon: "\u{1F4AA}", value: "42", label: "Strength"),
                    .init(icon: "\u{26A1}", value: "28", label: "Vitality"),
                    .init(icon: "\u{1F9E0}", value: "35", label: "Agility")
                ])

                // Lift cards
                AriseSectionHeader(title: "The Big 3")

                VStack(spacing: 0) {
                    LiftStatCard(name: "Back Squat", e1rm: 270, bodyweightMultiplier: 1.63, rank: .c)
                    LiftStatCard(name: "Bench Press", e1rm: 185, bodyweightMultiplier: 1.11, rank: .d)
                    LiftStatCard(name: "Deadlift", e1rm: 239, bodyweightMultiplier: 1.44, rank: .d)
                }

                // Currency
                CurrencyDisplayView(gold: 1250, points: 850)

                // Accessories grid
                AriseSectionHeader(title: "Accessories")

                LazyVGrid(columns: [
                    GridItem(.flexible()),
                    GridItem(.flexible()),
                    GridItem(.flexible())
                ], spacing: 12) {
                    AccessoryCard(name: "Biceps", isCompleted: true)
                    AccessoryCard(name: "Triceps", isCompleted: true)
                    AccessoryCard(name: "Shoulders", isCompleted: false)
                    AccessoryCard(name: "Back", isCompleted: true)
                    AccessoryCard(name: "Core", isCompleted: false)
                    AccessoryCard(name: "Calves", isCompleted: false)
                }
            }
            .padding(24)
        }
    }
}
