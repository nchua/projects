import ActivityKit
import Foundation

/// ActivityKit attributes for the Depart live activity.
/// Static content that doesn't change during the activity lifecycle.
struct DepartLiveActivityAttributes: ActivityAttributes {
    /// Dynamic content that updates during the activity.
    struct ContentState: Codable, Hashable {
        var minutesRemaining: Int
        var departureTime: Date
        var etaMinutes: Int
        var trafficStatus: String // "light", "moderate", "heavy", "severe"
        var isOverdue: Bool
    }

    // Static attributes
    let tripId: UUID
    let tripName: String
    let destination: String
    let arrivalTime: Date
    let travelMode: String
}
