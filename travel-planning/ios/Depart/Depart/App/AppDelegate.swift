import UIKit
import UserNotifications

/// UIApplicationDelegate for push notification registration, background tasks,
/// and UNUserNotificationCenter delegation.
class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // 1. Set notification delegate
        UNUserNotificationCenter.current().delegate = self

        // 2. Register notification categories (Navigate, Snooze, I've Left)
        NotificationManager.shared.configure()

        // 3. Register for remote notifications
        application.registerForRemoteNotifications()

        // Phase C TODO: FirebaseApp.configure() and Messaging.messaging().delegate setup

        return true
    }

    // MARK: - Push Token

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        // Phase C TODO: Forward APNs token to Firebase Messaging:
        //   Messaging.messaging().apnsToken = deviceToken
        // Then use FCM token (Messaging.messaging().token()) to register with backend.
        //
        // For now, log the raw APNs token:
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("[AppDelegate] APNs device token: \(tokenString.prefix(20))...")

        // Register with backend using the APNs token as a placeholder
        // (will switch to FCM token in Phase C when Firebase is integrated)
        Task {
            try? await APIClient.shared.registerDeviceToken(tokenString)
        }
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
        let actionId = response.actionIdentifier

        // Default tap — deep link to trip detail
        if actionId == UNNotificationDefaultActionIdentifier {
            if let destination = DeepLinkHandler.destination(from: userInfo) {
                DispatchQueue.main.async {
                    NotificationCenter.default.post(
                        name: .handleDeepLink,
                        object: destination
                    )
                }
            }
            completionHandler()
            return
        }

        // Action buttons — delegate to NotificationManager
        NotificationManager.shared.handleNotificationAction(
            response: response,
            apiClient: APIClient.shared
        )

        // Deep link after action if it opens the app
        if actionId == NotificationManager.navigateAction {
            // Navigate already opens Maps, no deep link needed
        } else if let destination = DeepLinkHandler.destination(from: userInfo) {
            DispatchQueue.main.async {
                NotificationCenter.default.post(
                    name: .handleDeepLink,
                    object: destination
                )
            }
        }

        completionHandler()
    }

    // MARK: - Background Silent Push

    func application(
        _ application: UIApplication,
        didReceiveRemoteNotification userInfo: [AnyHashable: Any],
        fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
    ) {
        // Parse server push data and schedule local notification as failsafe.
        // Backend push payload keys: trip_id, tier, recommended_departure, eta_seconds
        guard let tripIdString = userInfo["trip_id"] as? String,
              let tripId = UUID(uuidString: tripIdString),
              let departureStr = userInfo["recommended_departure"] as? String
        else {
            completionHandler(.noData)
            return
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fireDate = formatter.date(from: departureStr) ?? Date()
        let tier = (userInfo["tier"] as? String).flatMap(NotificationType.init(rawValue:)) ?? .leaveNow

        Task {
            await NotificationManager.shared.scheduleLocalNotification(
                tripId: tripId,
                title: "Time to leave",
                body: "Leave now to arrive on time.",
                fireDate: fireDate,
                tier: tier
            )
            completionHandler(.newData)
        }
    }
}

extension Notification.Name {
    static let handleDeepLink = Notification.Name("com.depart.handleDeepLink")
}
