import Foundation
import UserNotifications
import UIKit

@MainActor
class NotificationManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()

    @Published var isAuthorized = false
    @Published var pendingDeepLink: String?

    private var deviceTokenHex: String?

    override private init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
        Task { await checkAuthorizationStatus() }
    }

    // MARK: - Authorization

    func requestAuthorization() async {
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(
                options: [.alert, .badge, .sound]
            )
            isAuthorized = granted
            if granted {
                await MainActor.run {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        } catch {
            print("DEBUG: Notification authorization error: \(error)")
        }
    }

    func checkAuthorizationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        isAuthorized = settings.authorizationStatus == .authorized
    }

    // MARK: - Device Token Registration

    func registerDeviceToken(_ tokenData: Data) {
        let hex = tokenData.map { String(format: "%02x", $0) }.joined()
        deviceTokenHex = hex
        print("DEBUG: Device token registered: \(hex.prefix(16))...")

        Task {
            do {
                try await APIClient.shared.registerDeviceToken(hex)
            } catch {
                print("DEBUG: Failed to register device token with backend: \(error)")
            }
        }
    }

    func deactivateDeviceToken() async {
        guard let hex = deviceTokenHex else { return }
        do {
            try await APIClient.shared.deactivateDeviceToken(hex)
        } catch {
            print("DEBUG: Failed to deactivate device token: \(error)")
        }
    }

    // MARK: - Local Notification Schedulers

    func scheduleStreakAtRiskNotification(currentStreak: Int) {
        guard currentStreak > 0 else { return }

        cancelNotification(identifier: "streak_at_risk")

        let content = UNMutableNotificationContent()
        content.title = "STREAK WARNING"
        content.body = "Complete a quest today to maintain your \(currentStreak)-day streak!"
        content.sound = .default
        content.userInfo = ["type": "streak_at_risk"]

        // 8 PM today
        var dateComponents = Calendar.current.dateComponents([.year, .month, .day], from: Date())
        dateComponents.hour = 20
        dateComponents.minute = 0

        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: false)
        let request = UNNotificationRequest(identifier: "streak_at_risk", content: content, trigger: trigger)

        UNUserNotificationCenter.current().add(request) { error in
            if let error { print("DEBUG: Failed to schedule streak notification: \(error)") }
        }
    }

    func scheduleQuestResetNotification() {
        cancelNotification(identifier: "quest_reset")

        let content = UNMutableNotificationContent()
        content.title = "DAILY QUESTS RESET"
        content.body = "New daily quests are available. Begin today's training."
        content.sound = .default
        content.userInfo = ["type": "quest_reset"]

        // 7 AM daily
        var dateComponents = DateComponents()
        dateComponents.hour = 7
        dateComponents.minute = 0

        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: true)
        let request = UNNotificationRequest(identifier: "quest_reset", content: content, trigger: trigger)

        UNUserNotificationCenter.current().add(request) { error in
            if let error { print("DEBUG: Failed to schedule quest reset notification: \(error)") }
        }
    }

    func scheduleDungeonExpiringNotification(name: String, expiresAt: Date) {
        let identifier = "dungeon_expiring_\(name.hashValue)"
        cancelNotification(identifier: identifier)

        // 6 hours before expiry
        let fireDate = expiresAt.addingTimeInterval(-6 * 3600)
        guard fireDate > Date() else { return }

        let content = UNMutableNotificationContent()
        content.title = "DUNGEON EXPIRING"
        content.body = "\"\(name)\" closes in 6 hours. Enter before the gate seals."
        content.sound = .default
        content.userInfo = ["type": "dungeon_expiring"]

        let trigger = UNTimeIntervalNotificationTrigger(
            timeInterval: fireDate.timeIntervalSinceNow,
            repeats: false
        )
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)

        UNUserNotificationCenter.current().add(request) { error in
            if let error { print("DEBUG: Failed to schedule dungeon expiring notification: \(error)") }
        }
    }

    func scheduleMissionExpiringNotification(weekEnd: Date) {
        cancelNotification(identifier: "mission_expiring")

        // 1 day before week end
        let fireDate = weekEnd.addingTimeInterval(-24 * 3600)
        guard fireDate > Date() else { return }

        let content = UNMutableNotificationContent()
        content.title = "MISSION EXPIRING"
        content.body = "Your weekly mission ends tomorrow. Complete remaining workouts."
        content.sound = .default
        content.userInfo = ["type": "mission_expiring"]

        let trigger = UNTimeIntervalNotificationTrigger(
            timeInterval: fireDate.timeIntervalSinceNow,
            repeats: false
        )
        let request = UNNotificationRequest(identifier: "mission_expiring", content: content, trigger: trigger)

        UNUserNotificationCenter.current().add(request) { error in
            if let error { print("DEBUG: Failed to schedule mission expiring notification: \(error)") }
        }
    }

    func sendQuestCompletedNotification(questName: String, xpReward: Int) {
        let content = UNMutableNotificationContent()
        content.title = "QUEST COMPLETED"
        content.body = "\(questName) — +\(xpReward) XP earned."
        content.sound = .default
        content.userInfo = ["type": "quest_completed"]

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        let request = UNNotificationRequest(
            identifier: "quest_completed_\(UUID().uuidString)",
            content: content,
            trigger: trigger
        )

        UNUserNotificationCenter.current().add(request) { error in
            if let error { print("DEBUG: Failed to send quest completed notification: \(error)") }
        }
    }

    // MARK: - Cancel Helpers

    func cancelNotification(identifier: String) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [identifier])
    }

    func cancelStreakReminder() {
        cancelNotification(identifier: "streak_at_risk")
    }

    func cancelAllPendingNotifications() {
        UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
    }

    // MARK: - UNUserNotificationCenterDelegate

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Show banner even when app is in foreground
        completionHandler([.banner, .sound])
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        if let type = userInfo["type"] as? String {
            Task { @MainActor in
                self.pendingDeepLink = type
            }
        }
        completionHandler()
    }
}
