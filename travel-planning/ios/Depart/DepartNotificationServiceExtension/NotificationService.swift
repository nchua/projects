import MapKit
import UserNotifications

/// Notification Service Extension — intercepts push notifications before display.
/// Uses the ~30-second execution window to refresh ETA via MKDirections,
/// updating the notification body if the ETA differs by more than 3 minutes.
class NotificationService: UNNotificationServiceExtension {

    var contentHandler: ((UNNotificationContent) -> Void)?
    var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(
        _ request: UNNotificationRequest,
        withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)

        guard let bestAttemptContent else {
            contentHandler(request.content)
            return
        }

        let userInfo = request.content.userInfo

        // Extract coordinates from push payload
        guard let originLat = userInfo["origin_lat"] as? Double,
              let originLng = userInfo["origin_lng"] as? Double,
              let destLat = userInfo["dest_lat"] as? Double,
              let destLng = userInfo["dest_lng"] as? Double,
              let serverEtaStr = userInfo["eta_seconds"] as? String,
              let serverEtaSeconds = Int(serverEtaStr)
        else {
            contentHandler(bestAttemptContent)
            return
        }

        // Compute fresh ETA on-device
        let origin = MKMapItem(placemark: MKPlacemark(
            coordinate: CLLocationCoordinate2D(latitude: originLat, longitude: originLng)
        ))
        let destination = MKMapItem(placemark: MKPlacemark(
            coordinate: CLLocationCoordinate2D(latitude: destLat, longitude: destLng)
        ))

        let request = MKDirections.Request()
        request.source = origin
        request.destination = destination
        request.transportType = transportType(from: userInfo)

        let directions = MKDirections(request: request)

        Task {
            do {
                let eta = try await directions.calculateETA()
                let freshETASeconds = Int(eta.expectedTravelTime)
                let difference = abs(freshETASeconds - serverEtaSeconds)

                // Update notification body if ETA changed significantly (> 3 min)
                if difference > 180 {
                    let freshMinutes = freshETASeconds / 60
                    let bufferMin = (userInfo["buffer_minutes"] as? Int) ?? 0

                    let timeFormatter = DateFormatter()
                    timeFormatter.dateFormat = "h:mm a"

                    // Compute departure time from arrival time if available, otherwise estimate from now
                    var departureTimeStr = ""
                    if let arrivalTimeStr = userInfo["arrival_time"] as? String {
                        let isoFormatter = ISO8601DateFormatter()
                        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                        if let arrivalDate = isoFormatter.date(from: arrivalTimeStr) {
                            let departureTime = arrivalDate.addingTimeInterval(
                                -TimeInterval(freshETASeconds + bufferMin * 60)
                            )
                            departureTimeStr = timeFormatter.string(from: departureTime)
                        }
                    }

                    if departureTimeStr.isEmpty {
                        bestAttemptContent.body = "Updated: \(freshMinutes) min drive."
                    } else {
                        bestAttemptContent.body = "Updated: \(freshMinutes) min drive. Leave by \(departureTimeStr)."
                    }
                }
            } catch {
                // Use server ETA if MKDirections fails
                print("[NotificationService] ETA refresh failed: \(error)")
            }

            contentHandler(bestAttemptContent)
        }
    }

    override func serviceExtensionTimeWillExpire() {
        // Deliver whatever we have before the system kills us
        if let contentHandler, let bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }

    // MARK: - Helpers

    private func transportType(from userInfo: [AnyHashable: Any]) -> MKDirectionsTransportType {
        guard let mode = userInfo["travel_mode"] as? String else { return .automobile }
        switch mode {
        case "transit": return .transit
        case "walking": return .walking
        default: return .automobile
        }
    }
}
