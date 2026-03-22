import Foundation

/// Parses push notification userInfo into navigation destinations.
enum DeepLinkHandler {
    /// Parse push notification payload into a deep link destination.
    /// Backend sends: trip_id, tier, recommended_departure, eta_seconds, deep_link
    static func destination(from userInfo: [AnyHashable: Any]) -> DeepLinkDestination? {
        // Try trip_id from push payload
        if let tripIdString = userInfo["trip_id"] as? String,
           let tripId = UUID(uuidString: tripIdString) {
            return .tripDetail(tripId)
        }

        // Try deep_link URL
        if let deepLink = userInfo["deep_link"] as? String,
           let url = URL(string: deepLink),
           url.pathComponents.contains("trips"),
           let idString = url.pathComponents.last,
           let tripId = UUID(uuidString: idString) {
            return .tripDetail(tripId)
        }

        return nil
    }
}
