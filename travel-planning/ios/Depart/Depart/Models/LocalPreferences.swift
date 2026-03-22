import Foundation

/// Client-side preferences stored in UserDefaults (not synced to backend).
/// Backend-synced preferences (buffer, travel_mode, quiet_hours, timezone) live in UserProfile.
struct LocalPreferences: Codable {
    var preferredMapApp: MapApp = .apple
    var hapticFeedbackEnabled: Bool = true
    var pushNotificationsEnabled: Bool = true

    static let userDefaultsKey = "com.depart.localPreferences"

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: Self.userDefaultsKey)
        }
    }

    static func load() -> LocalPreferences {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let prefs = try? JSONDecoder().decode(LocalPreferences.self, from: data)
        else {
            return LocalPreferences()
        }
        return prefs
    }
}

enum MapApp: String, Codable, CaseIterable {
    case apple
    case google
    case waze

    var displayName: String {
        switch self {
        case .apple: return "Apple Maps"
        case .google: return "Google Maps"
        case .waze: return "Waze"
        }
    }
}
