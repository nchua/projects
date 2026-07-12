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
            #if DEBUG
            print("DEBUG: Notification authorization error: \(error)")
            #endif
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
        #if DEBUG
        print("DEBUG: Device token registered: \(hex.prefix(16))...")
        #endif

        Task {
            do {
                try await APIClient.shared.registerDeviceToken(hex)
            } catch {
                #if DEBUG
                print("DEBUG: Failed to register device token with backend: \(error)")
                #endif
            }
        }
    }

    func deactivateDeviceToken() async {
        guard let hex = deviceTokenHex else { return }
        do {
            try await APIClient.shared.deactivateDeviceToken(hex)
        } catch {
            #if DEBUG
            print("DEBUG: Failed to deactivate device token: \(error)")
            #endif
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
            #if DEBUG
            if let error { print("DEBUG: Failed to schedule streak notification: \(error)") }
            #endif
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
