import Foundation

// MARK: - Auth

/// Matches backend `app/schemas/auth.py` AuthResponse exactly.
struct AuthResponse: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let user: UserProfile
}

struct RegisterRequest: Codable {
    let email: String
    let password: String
    let displayName: String?
    let timezone: String
}

struct LoginRequest: Codable {
    let email: String
    let password: String
}

struct RefreshTokenRequest: Codable {
    let refreshToken: String
}

// MARK: - Trips

/// Matches backend `app/schemas/trip.py` PaginatedTripResponse exactly.
/// Field is "items" NOT "trips".
struct PaginatedTripResponse: Codable {
    let items: [Trip]
    let total: Int
    let limit: Int
    let offset: Int
}

/// Matches backend `app/schemas/trip.py` TripDetailResponse exactly.
/// FLAT structure — all Trip fields at root level plus eta_snapshots and notifications.
struct TripDetailResponse: Codable {
    // All Trip fields (flat, not nested)
    let id: UUID
    var name: String
    var originAddress: String
    var originLat: Double
    var originLng: Double
    var originLocationId: UUID?
    var originIsCurrentLocation: Bool
    var destAddress: String
    var destLat: Double
    var destLng: Double
    var destLocationId: UUID?
    var arrivalTime: Date
    var travelMode: String
    var bufferMinutes: Int
    var status: String
    var monitoringStartedAt: Date?
    var lastEtaSeconds: Int?
    var lastCheckedAt: Date?
    var notifyAt: Date?
    var baselineDurationSeconds: Int?
    var notified: Bool
    var notificationCount: Int
    var isRecurring: Bool
    var recurrenceRule: [String: AnyCodableValue]?
    var calendarEventId: String?
    var createdAt: Date
    var updatedAt: Date

    // Detail-specific fields
    var etaSnapshots: [EtaSnapshot]
    var notifications: [NotificationLogEntry]

    /// Convert to Trip model for use in views.
    var asTrip: Trip {
        Trip(
            id: id,
            name: name,
            originAddress: originAddress,
            originLat: originLat,
            originLng: originLng,
            originLocationId: originLocationId,
            originIsCurrentLocation: originIsCurrentLocation,
            destAddress: destAddress,
            destLat: destLat,
            destLng: destLng,
            destLocationId: destLocationId,
            arrivalTime: arrivalTime,
            travelMode: travelMode,
            bufferMinutes: bufferMinutes,
            status: status,
            monitoringStartedAt: monitoringStartedAt,
            lastEtaSeconds: lastEtaSeconds,
            lastCheckedAt: lastCheckedAt,
            notifyAt: notifyAt,
            baselineDurationSeconds: baselineDurationSeconds,
            notified: notified,
            notificationCount: notificationCount,
            isRecurring: isRecurring,
            recurrenceRule: recurrenceRule,
            calendarEventId: calendarEventId,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

/// Request body for POST /api/v1/trips.
/// Matches backend `app/schemas/trip.py` CreateTripRequest.
struct CreateTripRequest: Codable {
    let name: String
    let originAddress: String?
    let originLat: Double?
    let originLng: Double?
    let originLocationId: UUID?
    let originIsCurrentLocation: Bool
    let destAddress: String
    let destLat: Double
    let destLng: Double
    let destLocationId: UUID?
    let arrivalTime: Date
    let travelMode: String?
    let bufferMinutes: Int?
    let isRecurring: Bool
    let recurrenceRule: [String: AnyCodableValue]?
    let calendarEventId: String?
}

/// Request body for PUT /api/v1/trips/{id}.
/// Matches backend `app/schemas/trip.py` UpdateTripRequest. All fields optional.
struct UpdateTripRequest: Codable {
    var name: String?
    var originAddress: String?
    var originLat: Double?
    var originLng: Double?
    var originLocationId: UUID?
    var originIsCurrentLocation: Bool?
    var destAddress: String?
    var destLat: Double?
    var destLng: Double?
    var destLocationId: UUID?
    var arrivalTime: Date?
    var travelMode: String?
    var bufferMinutes: Int?
    var status: String? // Only "cancelled" or "departed" allowed
    var isRecurring: Bool?
    var recurrenceRule: [String: AnyCodableValue]?
}

// MARK: - Saved Locations

/// Matches backend `app/schemas/saved_location.py` CreateSavedLocationRequest.
struct CreateSavedLocationRequest: Codable {
    let name: String
    let address: String
    let latitude: Double
    let longitude: Double
    let icon: String?
    let sortOrder: Int
}

/// Matches backend `app/schemas/saved_location.py` UpdateSavedLocationRequest.
struct UpdateSavedLocationRequest: Codable {
    var name: String?
    var address: String?
    var latitude: Double?
    var longitude: Double?
    var icon: String?
    var sortOrder: Int?
}

// MARK: - Device Tokens

/// Matches backend `app/schemas/device_token.py` RegisterDeviceTokenRequest.
struct RegisterDeviceTokenRequest: Codable {
    let token: String
    let platform: String
}

/// Matches backend `app/schemas/device_token.py` UnregisterDeviceTokenRequest.
/// NOTE: Backend expects this in the DELETE request body.
struct UnregisterDeviceTokenRequest: Codable {
    let token: String
}

struct DeviceTokenResponse: Codable {
    let id: UUID
    let token: String
    let platform: String
    let isActive: Bool
    let createdAt: Date
}

// MARK: - User

/// Matches backend `app/schemas/user.py` UpdateUserRequest.
struct UpdateUserRequest: Codable {
    var displayName: String?
    var defaultBufferMinutes: Int?
    var defaultTravelMode: String?
    var quietHoursStart: String? // "HH:MM"
    var quietHoursEnd: String?   // "HH:MM"
    var timezone: String?
}

// MARK: - Error

/// Backend error response format.
struct APIErrorResponse: Codable {
    let detail: String
}
