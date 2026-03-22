import Foundation

/// Parses push notification userInfo and URL schemes into navigation destinations.
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
           let url = URL(string: deepLink) {
            return destination(from: url)
        }

        return nil
    }

    /// Parse a URL into a deep link destination.
    /// Supports: depart://trips/{id}, depart://add-trip, depart://settings
    static func destination(from url: URL) -> DeepLinkDestination? {
        guard url.scheme == "depart" else { return nil }

        let pathComponents = url.pathComponents.filter { $0 != "/" }

        switch url.host {
        case "trips":
            if let idString = pathComponents.first,
               let tripId = UUID(uuidString: idString) {
                return .tripDetail(tripId)
            }
        case "add-trip":
            return .addTrip
        case "settings":
            return .settings
        default:
            // Try path-based: depart:///trips/{id}
            if pathComponents.first == "trips",
               let idString = pathComponents.dropFirst().first,
               let tripId = UUID(uuidString: idString) {
                return .tripDetail(tripId)
            }
        }

        return nil
    }
}
