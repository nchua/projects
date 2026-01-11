import SwiftUI

struct DungeonDetailSheet: View {
    let dungeonId: String
    @ObservedObject var viewModel: DungeonsViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showAbandonConfirm = false

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: false, glowIntensity: 0.03)

                if viewModel.isLoadingDetail {
                    LoadingView()
                } else if let dungeon = viewModel.selectedDungeon {
                    DungeonDetailContent(
                        dungeon: dungeon,
                        viewModel: viewModel,
                        showAbandonConfirm: $showAbandonConfirm,
                        onDismiss: { dismiss() }
                    )
                } else {
                    ErrorView()
                }
            }
            .navigationTitle("Gate Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.voidDark, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                        .font(.ariseMono(size: 14, weight: .medium))
                        .foregroundColor(.systemPrimary)
                }
            }
            .alert("Abandon Dungeon?", isPresented: $showAbandonConfirm) {
                Button("Cancel", role: .cancel) {}
                Button("Abandon", role: .destructive) {
                    Task {
                        await viewModel.abandonDungeon(id: dungeonId)
                        dismiss()
                    }
                }
            } message: {
                Text("You will lose all progress and cannot re-enter this gate.")
            }
        }
        .task {
            await viewModel.loadDungeonDetail(id: dungeonId)
        }
    }
}

// MARK: - Loading View

private struct LoadingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .tint(.systemPrimary)
            Text("ANALYZING GATE...")
                .font(.ariseMono(size: 12, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(2)
        }
    }
}

// MARK: - Error View

private struct ErrorView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 32))
                .foregroundColor(.warningRed)
            Text("Gate data not found")
                .font(.ariseMono(size: 14))
                .foregroundColor(.textSecondary)
        }
    }
}

// MARK: - Dungeon Detail Content

private struct DungeonDetailContent: View {
    let dungeon: DungeonResponse
    @ObservedObject var viewModel: DungeonsViewModel
    @Binding var showAbandonConfirm: Bool
    var onDismiss: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Header
                DungeonDetailHeader(dungeon: dungeon)
                    .padding(.horizontal)

                // Time remaining bar (for active/available)
                if dungeon.status == "active" || dungeon.status == "available" {
                    TimeRemainingCard(dungeon: dungeon)
                        .padding(.horizontal)
                }

                // Objectives
                AriseSectionHeader(title: "Objectives")
                    .padding(.horizontal)

                ForEach(dungeon.objectives.sorted(by: { $0.orderIndex < $1.orderIndex })) { objective in
                    ObjectiveRow(objective: objective)
                        .padding(.horizontal)
                }

                // Rewards section
                DungeonRewardsCard(dungeon: dungeon)
                    .padding(.horizontal)

                // Action buttons
                DungeonActionButtons(
                    dungeon: dungeon,
                    viewModel: viewModel,
                    showAbandonConfirm: $showAbandonConfirm,
                    onDismiss: onDismiss
                )
                .padding(.horizontal)

                Spacer().frame(height: 40)
            }
            .padding(.vertical)
        }
    }
}

// MARK: - Dungeon Detail Header

struct DungeonDetailHeader: View {
    let dungeon: DungeonResponse

    var body: some View {
        VStack(spacing: 16) {
            // Top row: Rank + Status
            HStack {
                DungeonRankBadge(rank: dungeon.rank)

                VStack(alignment: .leading, spacing: 2) {
                    Text(dungeon.name)
                        .font(.ariseHeader(size: 20, weight: .bold))
                        .foregroundColor(.textPrimary)

                    HStack(spacing: 8) {
                        // Status tag
                        Text(dungeon.statusLabel)
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(dungeon.statusColor)
                            .tracking(1)

                        if dungeon.isBossDungeon {
                            BossTag()
                        }

                        if dungeon.isStretchDungeon {
                            StretchTag(percent: dungeon.stretchBonusPercent)
                        }
                    }
                }

                Spacer()
            }

            // Description
            Text(dungeon.description)
                .font(.ariseMono(size: 12))
                .foregroundColor(.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            // Progress bar
            if dungeon.status == "active" {
                VStack(spacing: 8) {
                    HStack {
                        Text("OBJECTIVES")
                            .font(.ariseMono(size: 10, weight: .semibold))
                            .foregroundColor(.textMuted)
                            .tracking(1)

                        Spacer()

                        Text("\(dungeon.requiredObjectivesComplete)/\(dungeon.totalRequiredObjectives)")
                            .font(.ariseMono(size: 12, weight: .semibold))
                            .foregroundColor(dungeon.requiredObjectivesComplete >= dungeon.totalRequiredObjectives ? .successGreen : .textPrimary)
                    }

                    AriseProgressBar(
                        progress: Double(dungeon.requiredObjectivesComplete) / Double(max(dungeon.totalRequiredObjectives, 1)),
                        color: dungeon.requiredObjectivesComplete >= dungeon.totalRequiredObjectives ? .successGreen : .systemPrimary,
                        height: 8
                    )
                }
            }
        }
        .padding(20)
        .background(Color.voidMedium)
        .overlay(
            Rectangle()
                .fill(dungeon.rankColor.opacity(0.3))
                .frame(height: 2),
            alignment: .top
        )
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Time Remaining Card

struct TimeRemainingCard: View {
    let dungeon: DungeonResponse

    var timeProgress: Double {
        // Calculate based on duration
        let totalSeconds = dungeon.durationHours * 3600
        let remaining = dungeon.timeRemainingSeconds
        return 1.0 - (Double(remaining) / Double(max(totalSeconds, 1)))
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                HStack(spacing: 6) {
                    Image(systemName: "clock.fill")
                        .font(.system(size: 14))
                        .foregroundColor(dungeon.isUrgent ? .warningRed : .textSecondary)

                    Text("TIME REMAINING")
                        .font(.ariseMono(size: 10, weight: .semibold))
                        .foregroundColor(.textMuted)
                        .tracking(1)
                }

                Spacer()

                Text(dungeon.timeRemainingFormatted)
                    .font(.ariseDisplay(size: 20, weight: .bold))
                    .foregroundColor(dungeon.isUrgent ? .warningRed : .textPrimary)
            }

            // Time progress bar (inverted - shows time elapsed)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.voidLight)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(dungeon.isUrgent ? Color.warningRed : Color.systemPrimary)
                        .frame(width: geometry.size.width * CGFloat(1.0 - timeProgress))
                }
            }
            .frame(height: 6)
        }
        .padding(16)
        .background(dungeon.isUrgent ? Color.warningRed.opacity(0.05) : Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(dungeon.isUrgent ? Color.warningRed.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Objective Row

struct ObjectiveRow: View {
    let objective: DungeonObjectiveResponse

    var body: some View {
        HStack(spacing: 12) {
            // Status icon
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(objective.isCompleted ? Color.successGreen : Color.voidLight)
                    .frame(width: 28, height: 28)

                if objective.isCompleted {
                    Image(systemName: "checkmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.voidBlack)
                } else {
                    Text("\(objective.progress)")
                        .font(.ariseMono(size: 11, weight: .semibold))
                        .foregroundColor(.textMuted)
                }
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(objective.name)
                        .font(.ariseHeader(size: 14, weight: .medium))
                        .foregroundColor(objective.isCompleted ? .textSecondary : .textPrimary)
                        .strikethrough(objective.isCompleted)

                    if !objective.isRequired {
                        Text("BONUS")
                            .font(.ariseMono(size: 8, weight: .bold))
                            .foregroundColor(.gold)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(Color.gold.opacity(0.15))
                            .cornerRadius(2)
                    }
                }

                Text(objective.description)
                    .font(.ariseMono(size: 11))
                    .foregroundColor(.textMuted)
                    .lineLimit(2)
            }

            Spacer()

            // Progress / XP
            VStack(alignment: .trailing, spacing: 2) {
                if !objective.isCompleted {
                    Text("\(objective.progress)/\(objective.targetValue)")
                        .font(.ariseMono(size: 12, weight: .semibold))
                        .foregroundColor(.textSecondary)
                }

                if objective.xpBonus > 0 {
                    HStack(spacing: 2) {
                        Text("+\(objective.xpBonus)")
                            .font(.ariseMono(size: 10, weight: .medium))
                            .foregroundColor(.gold)
                        Text("XP")
                            .font(.ariseMono(size: 8))
                            .foregroundColor(.textMuted)
                    }
                }
            }
        }
        .padding(14)
        .background(objective.isCompleted ? Color.successGreen.opacity(0.05) : Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(objective.isCompleted ? Color.successGreen.opacity(0.3) : Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Dungeon Rewards Card

struct DungeonRewardsCard: View {
    let dungeon: DungeonResponse

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("[ REWARDS ]")
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.gold)
                    .tracking(1)

                Spacer()
            }

            HStack(spacing: 24) {
                RewardItem(label: "BASE XP", value: "\(dungeon.baseXpReward)", color: .systemPrimary)

                if dungeon.isStretchDungeon, let percent = dungeon.stretchBonusPercent {
                    RewardItem(label: "STRETCH BONUS", value: "+\(percent)%", color: .gold)
                }

                RewardItem(label: "TOTAL XP", value: "\(dungeon.totalXpReward)", color: .gold)
            }
        }
        .padding(16)
        .background(Color.gold.opacity(0.05))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.gold.opacity(0.2), lineWidth: 1)
        )
    }
}

struct RewardItem: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.ariseMono(size: 9, weight: .semibold))
                .foregroundColor(.textMuted)
                .tracking(0.5)

            Text(value)
                .font(.ariseDisplay(size: 20, weight: .bold))
                .foregroundColor(color)
        }
    }
}

// MARK: - Dungeon Action Buttons

struct DungeonActionButtons: View {
    let dungeon: DungeonResponse
    @ObservedObject var viewModel: DungeonsViewModel
    @Binding var showAbandonConfirm: Bool
    var onDismiss: () -> Void

    var canClaim: Bool {
        dungeon.status == "completed" ||
        (dungeon.status == "active" && dungeon.requiredObjectivesComplete >= dungeon.totalRequiredObjectives)
    }

    var body: some View {
        VStack(spacing: 12) {
            // Primary action
            if dungeon.status == "available" {
                AcceptButton(viewModel: viewModel, dungeonId: dungeon.id)
            } else if canClaim {
                ClaimButton(viewModel: viewModel, dungeonId: dungeon.id, onDismiss: onDismiss)
            }

            // Secondary action (abandon)
            if dungeon.status == "active" && !canClaim {
                Button {
                    showAbandonConfirm = true
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "xmark.circle")
                            .font(.system(size: 12))
                        Text("ABANDON DUNGEON")
                            .font(.ariseMono(size: 12, weight: .semibold))
                            .tracking(1)
                    }
                    .foregroundColor(.warningRed)
                }
                .disabled(viewModel.isAbandoning)
            }
        }
    }
}

private struct AcceptButton: View {
    @ObservedObject var viewModel: DungeonsViewModel
    let dungeonId: String

    var body: some View {
        Button {
            Task { await viewModel.acceptDungeon(id: dungeonId) }
        } label: {
            HStack(spacing: 8) {
                if viewModel.isAccepting {
                    ProgressView()
                        .tint(.voidBlack)
                    Text("ENTERING...")
                } else {
                    Image(systemName: "door.left.hand.open")
                    Text("ENTER DUNGEON")
                }
            }
            .font(.ariseHeader(size: 14, weight: .semibold))
            .tracking(2)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Color.systemPrimary)
            .foregroundColor(.voidBlack)
        }
        .disabled(viewModel.isAccepting)
    }
}

private struct ClaimButton: View {
    @ObservedObject var viewModel: DungeonsViewModel
    let dungeonId: String
    var onDismiss: () -> Void

    var body: some View {
        Button {
            Task {
                await viewModel.claimReward(id: dungeonId)
                onDismiss()
            }
        } label: {
            HStack(spacing: 8) {
                if viewModel.isClaiming {
                    ProgressView()
                        .tint(.voidBlack)
                    Text("CLAIMING...")
                } else {
                    Image(systemName: "gift.fill")
                    Text("CLAIM REWARD")
                }
            }
            .font(.ariseHeader(size: 14, weight: .semibold))
            .tracking(2)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(Color.gold)
            .foregroundColor(.voidBlack)
        }
        .disabled(viewModel.isClaiming)
    }
}

// MARK: - Preview

#Preview {
    Text("Dungeon Detail Sheet")
}
