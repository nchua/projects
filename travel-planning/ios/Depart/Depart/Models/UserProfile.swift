import Foundation

/// Matches backend `app/models/enums.py` AuthProvider exactly.
enum AuthProvider: String, Codable {
    case email
    case apple
}

/// Matches backend `app/schemas/user.py` UserResponse exactly.
struct UserProfile: Codable {
    let id: UUID
    let email: String
    let displayName: String?
    let authProvider: String
    let defaultBufferMinutes: Int
    let defaultTravelMode: String
    let quietHoursStart: String? // "HH:MM" format
    let quietHoursEnd: String?   // "HH:MM" format
    let timezone: String
    let createdAt: Date
}

extension UserProfile {
    var authProviderEnum: AuthProvider {
        AuthProvider(rawValue: authProvider) ?? .email
    }

    var travelModeEnum: TravelMode {
        TravelMode(rawValue: defaultTravelMode) ?? .driving
    }
}
