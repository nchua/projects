import Foundation

/// Matches backend `app/schemas/trip.py` EtaSnapshotResponse exactly.
struct EtaSnapshot: Identifiable, Codable {
    let id: UUID
    let checkedAt: Date
    let durationSeconds: Int
    let durationInTrafficSeconds: Int
    let trafficModel: String
    let congestionLevel: String
    let distanceMeters: Int?
}

extension EtaSnapshot {
    var congestionLevelEnum: CongestionLevel {
        CongestionLevel(rawValue: congestionLevel) ?? .unknown
    }

    /// Travel time with traffic in minutes.
    var travelMinutes: Int {
        durationInTrafficSeconds / 60
    }

    /// Travel time without traffic in minutes.
    var baseTravelMinutes: Int {
        durationSeconds / 60
    }

    /// Delay caused by traffic in minutes.
    var trafficDelayMinutes: Int {
        max(0, travelMinutes - baseTravelMinutes)
    }
}
