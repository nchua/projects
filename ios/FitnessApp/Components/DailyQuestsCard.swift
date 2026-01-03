import SwiftUI

/// Daily quests card showing 3 quests with progress
struct DailyQuestsCard: View {
    let quests: [QuestResponse]
    let refreshAt: String
    let onClaim: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "scroll.fill")
                        .font(.system(size: 14))
                        .foregroundColor(.systemPrimary)

                    Text("DAILY QUESTS")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .foregroundColor(.textSecondary)
                        .tracking(1)
                }

                Spacer()

                RefreshTimerView(refreshAt: refreshAt)
            }

            // Quest rows
            VStack(spacing: 12) {
                ForEach(quests) { quest in
                    DailyQuestRow(quest: quest, onClaim: onClaim)
                }
            }
        }
        .padding(16)
        .systemPanelStyle()
    }
}

/// Individual quest row with progress bar and claim button
struct DailyQuestRow: View {
    let quest: QuestResponse
    let onClaim: (String) -> Void

    var progressPercent: Double {
        guard quest.targetValue > 0 else { return 0 }
        return min(1.0, Double(quest.progress) / Double(quest.targetValue))
    }

    var difficultyColor: Color {
        switch quest.difficulty {
        case "easy": return .successGreen
        case "hard": return .warningRed
        default: return .systemPrimary
        }
    }

    var statusIcon: String {
        if quest.isClaimed {
            return "checkmark.seal.fill"
        } else if quest.isCompleted {
            return "gift.fill"
        } else {
            return "circle"
        }
    }

    var statusColor: Color {
        if quest.isClaimed {
            return .textMuted
        } else if quest.isCompleted {
            return .gold
        } else {
            return .textMuted
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Title row
            HStack(spacing: 8) {
                Image(systemName: statusIcon)
                    .font(.system(size: 14))
                    .foregroundColor(statusColor)

                Text(quest.name)
                    .font(.ariseHeader(size: 14, weight: .semibold))
                    .foregroundColor(quest.isClaimed ? .textMuted : .textPrimary)

                Spacer()

                // XP Reward
                HStack(spacing: 4) {
                    Text("+\(quest.xpReward)")
                        .font(.ariseMono(size: 12, weight: .bold))
                        .foregroundColor(quest.isClaimed ? .textMuted : .systemPrimary)

                    Text("XP")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }
            }

            // Description
            Text(quest.description)
                .font(.ariseMono(size: 11))
                .foregroundColor(.textMuted)
                .lineLimit(1)

            // Progress bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // Background
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.voidLight)
                        .frame(height: 6)

                    // Fill
                    RoundedRectangle(cornerRadius: 2)
                        .fill(quest.isCompleted ? Color.successGreen : difficultyColor)
                        .frame(width: geometry.size.width * progressPercent, height: 6)
                }
            }
            .frame(height: 6)

            // Bottom row: Progress text + Claim button
            HStack {
                Text("\(quest.progress)/\(quest.targetValue)")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.textMuted)

                Spacer()

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
                    .pulseGlow(color: .gold)
                } else if quest.isClaimed {
                    Text("CLAIMED")
                        .font(.ariseMono(size: 10, weight: .medium))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }
            }
        }
        .padding(12)
        .background(
            quest.isCompleted && !quest.isClaimed
            ? Color.gold.opacity(0.05)
            : Color.voidMedium
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(
                    quest.isCompleted && !quest.isClaimed
                    ? Color.gold.opacity(0.3)
                    : Color.ariseBorder,
                    lineWidth: 1
                )
        )
        .cornerRadius(4)
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
                        difficulty: "normal"
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
                        difficulty: "normal"
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
                        difficulty: "easy"
                    )
                ],
                refreshAt: ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600 * 8)),
                onClaim: { _ in }
            )
            .padding(.horizontal)
        }
    }
}
