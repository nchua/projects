import Foundation

// MARK: - Enums

/// Matches backend `app/models/enums.py` TravelMode exactly.
enum TravelMode: String, Codable, CaseIterable {
    case driving
    case transit
    case walking
    case cycling
}

/// Matches backend `app/models/enums.py` TripStatus exactly.
enum TripStatus: String, Codable {
    case pending
    case monitoring
    case notified
    case departed
    case completed
    case cancelled
}

/// Matches backend `app/models/enums.py` CongestionLevel exactly.
enum CongestionLevel: String, Codable {
    case unknown
    case light
    case moderate
    case heavy
    case severe

    var displayName: String {
        rawValue.capitalized
    }
}

// MARK: - Trip Model

/// Matches backend `app/schemas/trip.py` TripResponse exactly.
/// Uses convertFromSnakeCase key strategy on the decoder.
struct Trip: Identifiable, Codable, Hashable {
    let id: UUID
    var name: String

    // Origin
    var originAddress: String
    var originLat: Double
    var originLng: Double
    var originLocationId: UUID?
    var originIsCurrentLocation: Bool

    // Destination
    var destAddress: String
    var destLat: Double
    var destLng: Double
    var destLocationId: UUID?

    // Timing
    var arrivalTime: Date
    var travelMode: String // Raw string from backend (e.g., "driving")
    var bufferMinutes: Int

    // Monitoring state
    var status: String // Raw string from backend (e.g., "pending")
    var monitoringStartedAt: Date?
    var lastEtaSeconds: Int? // "lastEtaSeconds" matches convertFromSnakeCase("last_eta_seconds")
    var lastCheckedAt: Date?
    var notifyAt: Date?
    var baselineDurationSeconds: Int?
    var notified: Bool
    var notificationCount: Int

    // Recurrence
    var isRecurring: Bool
    var recurrenceRule: [String: AnyCodableValue]?

    // Calendar
    var calendarEventId: String?

    // Timestamps
    var createdAt: Date
    var updatedAt: Date
}

// MARK: - Trip Computed Properties

extension Trip {
    var travelModeEnum: TravelMode {
        TravelMode(rawValue: travelMode) ?? .driving
    }

    var statusEnum: TripStatus {
        TripStatus(rawValue: status) ?? .pending
    }

    /// Recommended departure time based on server-computed notifyAt.
    var departureTime: Date? {
        notifyAt
    }

    /// Minutes until recommended departure. Negative if overdue.
    var minutesUntilDeparture: Int? {
        guard let departureTime else { return nil }
        return Int(departureTime.timeIntervalSinceNow / 60)
    }

    /// Estimated travel time in minutes.
    var estimatedTravelMinutes: Int? {
        guard let lastEtaSeconds else { return nil }
        return lastEtaSeconds / 60
    }

    /// Status color category for dashboard display.
    var urgencyLevel: UrgencyLevel {
        guard let minutes = minutesUntilDeparture else { return .normal }
        if minutes < 0 { return .overdue }
        if minutes < 10 { return .critical }
        if minutes < 30 { return .warning }
        return .normal
    }

    enum UrgencyLevel {
        case normal   // > 30 min — green
        case warning  // 10-30 min — yellow
        case critical // < 10 min — red
        case overdue  // past departure — red
    }
}

// MARK: - AnyCodableValue

/// Lightweight wrapper for encoding/decoding untyped JSON values (for recurrence_rule JSONB).
enum AnyCodableValue: Codable, Hashable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([AnyCodableValue])
    case dictionary([String: AnyCodableValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([AnyCodableValue].self) {
            self = .array(value)
        } else if let value = try? container.decode([String: AnyCodableValue].self) {
            self = .dictionary(value)
        } else {
            self = .null
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .dictionary(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }
}
