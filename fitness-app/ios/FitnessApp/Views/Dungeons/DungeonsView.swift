import SwiftUI

struct DungeonsView: View {
    @StateObject private var viewModel = DungeonsViewModel()
    @State private var selectedDungeonId: String?
    @State private var showDungeonDetail = false

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.03)

                if viewModel.isLoading && viewModel.availableDungeons.isEmpty {
                    LoadingView()
                } else {
                    ScrollView {
                        VStack(spacing: 24) {
                            // Header
                            DungeonBoardHeader(
                                level: viewModel.userLevel,
                                rank: viewModel.hunterRank
                            )
                            .padding(.horizontal)

                            // Completed Dungeons (ready to claim)
                            if !viewModel.completedDungeons.isEmpty {
                                DungeonSection(
                                    title: "Rewards Ready",
                                    subtitle: "Claim your spoils",
                                    icon: "trophy.fill",
                                    iconColor: .gold,
                                    dungeons: viewModel.completedDungeons,
                                    onSelect: { id in
                                        selectedDungeonId = id
                                        showDungeonDetail = true
                                    }
                                )
                            }

                            // Active Dungeons
                            if !viewModel.activeDungeons.isEmpty {
                                DungeonSection(
                                    title: "Active Dungeons",
                                    subtitle: "Gates you've entered",
                                    icon: "flame.fill",
                                    iconColor: .gold,
                                    dungeons: viewModel.activeDungeons,
                                    onSelect: { id in
                                        selectedDungeonId = id
                                        showDungeonDetail = true
                                    }
                                )
                            }

                            // Available Dungeons
                            if !viewModel.availableDungeons.isEmpty {
                                DungeonSection(
                                    title: "Available Gates",
                                    subtitle: "Enter before they close",
                                    icon: "door.left.hand.open",
                                    iconColor: .systemPrimary,
                                    dungeons: viewModel.availableDungeons,
                                    onSelect: { id in
                                        selectedDungeonId = id
                                        showDungeonDetail = true
                                    }
                                )
                            }

                            // Empty state
                            if viewModel.availableDungeons.isEmpty &&
                               viewModel.activeDungeons.isEmpty &&
                               viewModel.completedDungeons.isEmpty {
                                EmptyDungeonsCard()
                                    .padding(.horizontal)
                            }

                            // Debug buttons (only in DEBUG)
                            #if DEBUG
                            DebugDungeonControls(viewModel: viewModel)
                                .padding(.horizontal)
                            #endif

                            Spacer().frame(height: 100)
                        }
                        .padding(.vertical)
                    }
                }
            }
            .navigationBarHidden(true)
            .refreshable {
                await viewModel.loadDungeons()
            }
        }
        .task {
            await viewModel.loadDungeons()
        }
        .sheet(isPresented: $showDungeonDetail) {
            if let dungeonId = selectedDungeonId {
                DungeonDetailSheet(
                    dungeonId: dungeonId,
                    viewModel: viewModel
                )
            }
        }
        .sheet(isPresented: $viewModel.showClaimResult) {
            if let result = viewModel.claimResult {
                DungeonRewardSheet(result: result)
            }
        }
    }
}

// MARK: - Loading View

private struct LoadingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .tint(.systemPrimary)
            Text("SCANNING FOR GATES...")
                .font(.ariseMono(size: 12, weight: .medium))
                .foregroundColor(.textMuted)
                .tracking(2)
        }
    }
}

// MARK: - Dungeon Board Header

struct DungeonBoardHeader: View {
    let level: Int
    let rank: HunterRank
    @State private var showContent = false

    var body: some View {
        VStack(spacing: 16) {
            // System tag
            HStack {
                Text("[ DUNGEON GATE BOARD ]")
                    .font(.ariseMono(size: 11, weight: .medium))
                    .foregroundColor(.systemPrimary)
                    .tracking(2)

                Spacer()

                // Level indicator
                HStack(spacing: 4) {
                    Text("LV")
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                    Text("\(level)")
                        .font(.ariseDisplay(size: 16, weight: .bold))
                        .foregroundColor(.systemPrimary)

                    RankBadgeView(rank: rank, size: .small)
                }
            }

            // Title
            HStack(spacing: 12) {
                Image(systemName: "door.left.hand.open")
                    .font(.system(size: 24))
                    .foregroundColor(.systemPrimary)
                    .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)

                VStack(alignment: .leading, spacing: 2) {
                    Text("Dungeon Gates")
                        .font(.ariseHeader(size: 22, weight: .bold))
                        .foregroundColor(.textPrimary)

                    Text("Complete objectives to earn rewards")
                        .font(.ariseMono(size: 11))
                        .foregroundColor(.textMuted)
                }

                Spacer()
            }
        }
        .padding(16)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
        .overlay(
            Rectangle()
                .fill(Color.systemPrimary.opacity(0.2))
                .frame(height: 1),
            alignment: .top
        )
        .opacity(showContent ? 1 : 0)
        .offset(y: showContent ? 0 : 10)
        .onAppear {
            withAnimation(.easeOut(duration: 0.5)) {
                showContent = true
            }
        }
    }
}

// MARK: - Dungeon Section

struct DungeonSection: View {
    let title: String
    let subtitle: String
    let icon: String
    let iconColor: Color
    let dungeons: [DungeonSummaryResponse]
    let onSelect: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Section header
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundColor(iconColor)

                VStack(alignment: .leading, spacing: 0) {
                    Text(title)
                        .font(.ariseHeader(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)

                    Text(subtitle)
                        .font(.ariseMono(size: 10))
                        .foregroundColor(.textMuted)
                }

                Spacer()

                Text("\(dungeons.count)")
                    .font(.ariseDisplay(size: 18, weight: .bold))
                    .foregroundColor(iconColor)
            }
            .padding(.horizontal)

            // Dungeon cards
            ForEach(Array(dungeons.enumerated()), id: \.element.id) { index, dungeon in
                DungeonCardView(dungeon: dungeon) {
                    onSelect(dungeon.id)
                }
                .padding(.horizontal)
                .fadeIn(delay: Double(index) * 0.05)
            }
        }
    }
}

// MARK: - Empty State

struct EmptyDungeonsCard: View {
    var body: some View {
        VStack(spacing: 20) {
            ZStack {
                Circle()
                    .fill(Color.voidLight)
                    .frame(width: 80, height: 80)

                ProgressView()
                    .tint(.systemPrimary)
            }

            VStack(spacing: 8) {
                Text("Scanning for Gates...")
                    .font(.ariseHeader(size: 18, weight: .semibold))
                    .foregroundColor(.textPrimary)

                Text("New dungeon gates are spawning.\nPull to refresh.")
                    .font(.ariseMono(size: 12))
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .padding(.horizontal, 24)
        .background(Color.voidMedium)
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.ariseBorder, lineWidth: 1)
        )
    }
}

// MARK: - Debug Controls

#if DEBUG
struct DebugDungeonControls: View {
    @ObservedObject var viewModel: DungeonsViewModel

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("[ DEBUG ]")
                    .font(.ariseMono(size: 10))
                    .foregroundColor(.warningRed)
                    .tracking(1)

                Spacer()
            }

            HStack(spacing: 12) {
                Button {
                    Task { await viewModel.forceSpawn() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "wand.and.stars")
                        Text("SPAWN")
                    }
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.systemPrimary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.systemPrimary.opacity(0.1))
                    .cornerRadius(4)
                }

                Button {
                    Task { await viewModel.forceSpawnRare() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                        Text("RARE")
                    }
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.gold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.gold.opacity(0.1))
                    .cornerRadius(4)
                }

                Button {
                    Task { await viewModel.seedDungeons() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "square.and.arrow.down")
                        Text("SEED")
                    }
                    .font(.ariseMono(size: 10, weight: .semibold))
                    .foregroundColor(.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.voidLight)
                    .cornerRadius(4)
                }

                Spacer()
            }
        }
        .padding(12)
        .background(Color.warningRed.opacity(0.05))
        .cornerRadius(4)
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.warningRed.opacity(0.2), lineWidth: 1)
        )
    }
}
#endif

// MARK: - Preview

#Preview {
    DungeonsView()
        .environmentObject(AuthManager.shared)
}
