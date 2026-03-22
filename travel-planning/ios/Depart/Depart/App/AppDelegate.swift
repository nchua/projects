import UIKit
import UserNotifications

/// UIApplicationDelegate for push notification registration, background tasks,
/// and UNUserNotificationCenter delegation.
/// Firebase configuration will be added in Phase C.
class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Set notification delegate
        UNUserNotificationCenter.current().delegate = self

        // Register for remote notifications
        application.registerForRemoteNotifications()

        return true
    }

    // MARK: - Push Token

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        // Phase C: Forward to Firebase Messaging, then register FCM token with backend
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("[AppDelegate] APNs device token: \(tokenString.prefix(20))...")
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        print("[AppDelegate] Failed to register for remote notifications: \(error)")
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// App is in foreground — still show banner + sound for trip alerts.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        let userInfo = notification.request.content.userInfo
        if userInfo["trip_id"] != nil {
            completionHandler([.banner, .sound, .badge])
        } else {
            completionHandler([])
        }
    }

    /// User tapped a notification or performed an action.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo

        switch response.actionIdentifier {
        case UNNotificationDefaultActionIdentifier:
            // Tap — deep link to trip detail
            if let destination = DeepLinkHandler.destination(from: userInfo) {
                DispatchQueue.main.async {
                    // Will be consumed by DepartApp via AppState.pendingDeepLink
                    NotificationCenter.default.post(
                        name: .handleDeepLink,
                        object: destination
                    )
                }
            }

        case "NAVIGATE":
            // Open Maps — handled in Phase C
            break

        case "SNOOZE":
            // Snooze 5 min — handled in Phase C
            break

        case "DEPARTED":
            // Mark as departed — handled in Phase C
            break

        default:
            break
        }

        completionHandler()
    }

    // MARK: - Background Silent Push

    func application(
        _ application: UIApplication,
        didReceiveRemoteNotification userInfo: [AnyHashable: Any],
        fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
    ) {
        // Phase C: Parse recommended_departure, schedule local notification as failsafe
        print("[AppDelegate] Received silent push")
        completionHandler(.newData)
    }
}

extension Notification.Name {
    static let handleDeepLink = Notification.Name("com.depart.handleDeepLink")
}
