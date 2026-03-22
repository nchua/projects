import Foundation
import MapKit
import UIKit
import UserNotifications

/// Manages push notification authorization, categories, local scheduling, and action handling.
@Observable
final class NotificationManager {
    static let shared = NotificationManager()

    var isAuthorized = false

    // Notification category identifiers
    static let tripAlertCategory = "TRIP_ALERT"
    static let tripAlertUrgentCategory = "TRIP_ALERT_URGENT"

    // Action identifiers
    static let navigateAction = "NAVIGATE"
    static let snoozeAction = "SNOOZE"
    static let departedAction = "DEPARTED"

    // MARK: - Setup

    /// Register notification categories and actions. Called from AppDelegate.didFinishLaunching.
    func configure() {
        // Standard trip alert: Navigate, Snooze 5 min, I've Left
        let standardCategory = UNNotificationCategory(
            identifier: Self.tripAlertCategory,
            actions: [
                UNNotificationAction(
                    identifier: Self.navigateAction,
                    title: "Navigate",
                    options: [.foreground]
                ),
                UNNotificationAction(
                    identifier: Self.snoozeAction,
                    title: "Snooze 5 min",
                    options: []
                ),
                UNNotificationAction(
                    identifier: Self.departedAction,
                    title: "I've Left",
                    options: [.destructive]
                ),
            ],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )

        // Urgent trip alert: Navigate Now, I've Left
        let urgentCategory = UNNotificationCategory(
            identifier: Self.tripAlertUrgentCategory,
            actions: [
                UNNotificationAction(
                    identifier: Self.navigateAction,
                    title: "Navigate Now",
                    options: [.foreground]
                ),
                UNNotificationAction(
                    identifier: Self.departedAction,
                    title: "I've Left",
                    options: [.destructive]
                ),
            ],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )

        UNUserNotificationCenter.current().setNotificationCategories([
            standardCategory, urgentCategory,
        ])
    }

    // MARK: - Authorization

    func requestAuthorization() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            isAuthorized = granted
            return granted
        } catch {
            print("[NotificationManager] Auth error: \(error)")
            isAuthorized = false
            return false
        }
    }

    func checkAuthorizationStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        isAuthorized = settings.authorizationStatus == .authorized
    }

    // MARK: - Local Notification Scheduling

    /// Schedule a local notification as a server-push failsafe.
    func scheduleLocalNotification(
        tripId: UUID,
        title: String,
        body: String,
        fireDate: Date,
        tier: NotificationType
    ) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.categoryIdentifier = tier.isUrgent
            ? Self.tripAlertUrgentCategory
            : Self.tripAlertCategory
        content.userInfo = [
            "trip_id": tripId.uuidString,
            "tier": tier.rawValue,
        ]
        content.sound = tier.notificationSound
        content.interruptionLevel = tier.interruptionLevel

        let dateComponents = Calendar.current.dateComponents(
            [.year, .month, .day, .hour, .minute, .second],
            from: fireDate
        )
        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: false)
        let identifier = "trip-\(tripId.uuidString)-\(tier.rawValue)"
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)

        do {
            try await UNUserNotificationCenter.current().add(request)
            print("[NotificationManager] Scheduled \(tier.rawValue) for trip \(tripId.uuidString.prefix(8)) at \(fireDate.shortTimeString)")
        } catch {
            print("[NotificationManager] Schedule error: \(error)")
        }
    }

    /// Cancel all notifications for a specific trip.
    func cancelNotifications(for tripId: UUID) {
        let center = UNUserNotificationCenter.current()
        let prefix = "trip-\(tripId.uuidString)"

        center.getPendingNotificationRequests { requests in
            let matching = requests
                .filter { $0.identifier.hasPrefix(prefix) }
                .map(\.identifier)
            center.removePendingNotificationRequests(withIdentifiers: matching)
            center.removeDeliveredNotifications(withIdentifiers: matching)
        }
    }

    // MARK: - Notification Action Handling

    /// Handle a notification action response. Called from AppDelegate.
    func handleNotificationAction(
        response: UNNotificationResponse,
        apiClient: APIClient
    ) {
        let userInfo = response.notification.request.content.userInfo
        guard let tripIdString = userInfo["trip_id"] as? String,
              let tripId = UUID(uuidString: tripIdString)
        else { return }

        switch response.actionIdentifier {
        case Self.navigateAction:
            openMapsForTrip(userInfo: userInfo)

        case Self.snoozeAction:
            Task {
                await snoozeTripFromNotification(tripId: tripId, apiClient: apiClient)
            }

        case Self.departedAction:
            Task {
                let update = UpdateTripRequest(status: "departed")
                let _ = try? await apiClient.updateTrip(tripId: tripId, update)
                cancelNotifications(for: tripId)
            }

        case UNNotificationDefaultActionIdentifier:
            // Default tap — deep link handled by AppDelegate
            break

        default:
            break
        }
    }

    // MARK: - Private

    private func openMapsForTrip(userInfo: [AnyHashable: Any]) {
        guard let destLatStr = userInfo["dest_lat"] as? String,
              let destLngStr = userInfo["dest_lng"] as? String,
              let destLat = Double(destLatStr),
              let destLng = Double(destLngStr)
        else { return }

        let coordinate = CLLocationCoordinate2D(latitude: destLat, longitude: destLng)
        let placemark = MKPlacemark(coordinate: coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = "Destination"
        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving,
        ])
    }

    private func snoozeTripFromNotification(tripId: UUID, apiClient: APIClient) async {
        // Fetch trip to get current arrival time, then add 5 minutes
        do {
            let detail = try await apiClient.fetchTripDetail(tripId: tripId)
            let newArrival = detail.arrivalTime.addingTimeInterval(5 * 60)
            let update = UpdateTripRequest(arrivalTime: newArrival)
            let _ = try await apiClient.updateTrip(tripId: tripId, update)
        } catch {
            print("[NotificationManager] Snooze failed: \(error)")
        }
    }
}

// MARK: - NotificationType Extensions

extension NotificationType {
    var interruptionLevel: UNNotificationInterruptionLevel {
        switch self {
        case .headsUp: return .passive
        case .prepare: return .active
        case .leaveSoon: return .timeSensitive
        case .leaveNow: return .timeSensitive // Use timeSensitive (not critical — requires Apple entitlement)
        case .runningLate: return .active
        }
    }

    var notificationSound: UNNotificationSound? {
        switch self {
        case .headsUp: return nil
        case .prepare: return .default
        case .leaveSoon: return .default
        case .leaveNow: return .defaultCritical
        case .runningLate: return .default
        }
    }
}
