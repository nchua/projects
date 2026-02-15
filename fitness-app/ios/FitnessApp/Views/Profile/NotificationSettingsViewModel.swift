import Foundation
import UserNotifications

@MainActor
class NotificationSettingsViewModel: ObservableObject {
    @Published var preferences: [String: Bool] = [:]
    @Published var isLoading = false
    @Published var error: String?
    @Published var systemNotificationsEnabled = true

    // All notification types in display order
    static let socialTypes = [
        ("friend_request_received", "Friend Request Received", "person.fill"),
        ("friend_request_accepted", "Friend Request Accepted", "person.2.fill"),
    ]

    static let progressionTypes = [
        ("achievement_unlocked", "Achievement Unlocked", "trophy.fill"),
        ("level_up", "Level Up", "arrow.up.circle.fill"),
        ("rank_promotion", "Rank Promotion", "shield.lefthalf.filled"),
        ("quest_completed", "Quest Completed", "checkmark.seal.fill"),
    ]

    static let missionTypes = [
        ("dungeon_spawned", "Dungeon Spawned", "door.left.hand.open"),
        ("weekly_report_ready", "Weekly Report Ready", "chart.bar.fill"),
        ("mission_offered", "Mission Offered", "scroll.fill"),
        ("streak_at_risk", "Streak at Risk", "flame.fill"),
        ("quest_reset", "Quest Reset", "arrow.clockwise"),
        ("dungeon_expiring", "Dungeon Expiring", "clock.badge.exclamationmark"),
        ("mission_expiring", "Mission Expiring", "calendar.badge.clock"),
    ]

    var allEnabled: Bool {
        let allTypes = Self.socialTypes + Self.progressionTypes + Self.missionTypes
        return allTypes.allSatisfy { preferences[$0.0] ?? true }
    }

    func loadPreferences() async {
        isLoading = true
        error = nil

        // Check system notification status
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        systemNotificationsEnabled = settings.authorizationStatus == .authorized

        do {
            let response = try await APIClient.shared.getNotificationPreferences()
            var prefs: [String: Bool] = [:]
            for pref in response.preferences {
                prefs[pref.notificationType] = pref.enabled
            }
            preferences = prefs
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func togglePreference(type: String) {
        let currentValue = preferences[type] ?? true
        preferences[type] = !currentValue

        Task {
            do {
                let update = NotificationPreferenceUpdate(
                    notificationType: type,
                    enabled: !currentValue
                )
                _ = try await APIClient.shared.updateNotificationPreferences([update])
            } catch {
                // Revert on failure
                preferences[type] = currentValue
                self.error = error.localizedDescription
            }
        }
    }

    func toggleAll() {
        let newValue = !allEnabled
        let allTypes = Self.socialTypes + Self.progressionTypes + Self.missionTypes

        // Optimistically update all
        for (type, _, _) in allTypes {
            preferences[type] = newValue
        }

        Task {
            do {
                let updates = allTypes.map { (type, _, _) in
                    NotificationPreferenceUpdate(notificationType: type, enabled: newValue)
                }
                _ = try await APIClient.shared.updateNotificationPreferences(updates)
            } catch {
                // Revert on failure
                await loadPreferences()
                self.error = error.localizedDescription
            }
        }
    }
}
