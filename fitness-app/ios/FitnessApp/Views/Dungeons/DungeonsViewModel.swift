import Foundation
import SwiftUI

@MainActor
class DungeonsViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var error: String?

    // Dungeon lists
    @Published var availableDungeons: [DungeonSummaryResponse] = []
    @Published var activeDungeons: [DungeonSummaryResponse] = []
    @Published var completedDungeons: [DungeonSummaryResponse] = []

    // User info
    @Published var userLevel: Int = 1
    @Published var userRank: String = "E"

    // Selected dungeon for detail view
    @Published var selectedDungeon: DungeonResponse?
    @Published var isLoadingDetail = false

    // Claim results
    @Published var claimResult: DungeonClaimResponse?
    @Published var showClaimResult = false

    // Actions in progress
    @Published var isAccepting = false
    @Published var isAbandoning = false
    @Published var isClaiming = false

    var hunterRank: HunterRank {
        HunterRank(rawValue: userRank) ?? .e
    }

    // MARK: - Load Data

    func loadDungeons() async {
        isLoading = true
        error = nil

        do {
            let response = try await APIClient.shared.getDungeons()
            availableDungeons = response.available
            activeDungeons = response.active
            completedDungeons = response.completedUnclaimed
            userLevel = response.userLevel
            userRank = response.userRank
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func loadDungeonDetail(id: String) async {
        isLoadingDetail = true

        do {
            selectedDungeon = try await APIClient.shared.getDungeon(id: id)
        } catch {
            self.error = error.localizedDescription
        }

        isLoadingDetail = false
    }

    // MARK: - Actions

    func acceptDungeon(id: String) async {
        isAccepting = true

        do {
            let response = try await APIClient.shared.acceptDungeon(id: id)
            selectedDungeon = response.dungeon

            // Refresh lists
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isAccepting = false
    }

    func abandonDungeon(id: String) async {
        isAbandoning = true

        do {
            _ = try await APIClient.shared.abandonDungeon(id: id)
            selectedDungeon = nil

            // Refresh lists
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isAbandoning = false
    }

    func claimReward(id: String) async {
        isClaiming = true

        do {
            claimResult = try await APIClient.shared.claimDungeonReward(id: id)
            showClaimResult = true

            // Refresh lists
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isClaiming = false
    }

    // MARK: - Debug

    func forceSpawn() async {
        isLoading = true

        do {
            _ = try await APIClient.shared.forceSpawnDungeon()
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func forceSpawnRare() async {
        isLoading = true

        do {
            _ = try await APIClient.shared.forceSpawnRareDungeon()
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func seedDungeons() async {
        isLoading = true

        do {
            try await APIClient.shared.seedDungeons()
            await loadDungeons()
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - Dungeon Helpers

extension DungeonSummaryResponse {
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

    var statusColor: Color {
        switch status {
        case "available": return .systemPrimary
        case "active": return .gold
        case "completed": return .successGreen
        case "failed", "expired", "abandoned": return .warningRed
        default: return .textMuted
        }
    }

    var statusLabel: String {
        switch status {
        case "available": return "AVAILABLE"
        case "active": return "IN PROGRESS"
        case "completed": return "COMPLETED"
        case "failed": return "FAILED"
        case "expired": return "EXPIRED"
        case "abandoned": return "ABANDONED"
        default: return status.uppercased()
        }
    }
}

extension DungeonResponse {
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

    var statusColor: Color {
        switch status {
        case "available": return .systemPrimary
        case "active": return .gold
        case "completed": return .successGreen
        case "failed", "expired", "abandoned": return .warningRed
        default: return .textMuted
        }
    }

    var statusLabel: String {
        switch status {
        case "available": return "AVAILABLE"
        case "active": return "IN PROGRESS"
        case "completed": return "COMPLETED"
        case "failed": return "FAILED"
        case "expired": return "EXPIRED"
        case "abandoned": return "ABANDONED"
        default: return status.uppercased()
        }
    }
}
