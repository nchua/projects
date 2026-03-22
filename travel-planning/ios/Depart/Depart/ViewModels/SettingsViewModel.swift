import Foundation
import SwiftUI

/// ViewModel for Settings screen.
@Observable
final class SettingsViewModel {
    // Saved locations
    var savedLocations: [SavedLocation] = []

    // Preferences
    var defaultBufferMinutes: Int = 10
    var defaultTravelMode: TravelMode = .driving
    var pushEnabled: Bool = true
    var hapticEnabled: Bool = true
    var quietHoursEnabled: Bool = false
    var quietHoursStart: Date = Calendar.current.date(from: DateComponents(hour: 22))!
    var quietHoursEnd: Date = Calendar.current.date(from: DateComponents(hour: 7))!

    // State
    var isLoading = false
    var error: String?

    private var apiClient: APIClient?
    private var saveTask: Task<Void, Never>?

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Load

    func loadPreferences() async {
        do {
            let profile = try await apiClient?.fetchProfile()
            if let profile {
                defaultBufferMinutes = profile.defaultBufferMinutes
                defaultTravelMode = profile.travelModeEnum

                if let start = profile.quietHoursStart {
                    quietHoursEnabled = true
                    quietHoursStart = parseTimeString(start) ?? quietHoursStart
                }
                if let end = profile.quietHoursEnd {
                    quietHoursEnd = parseTimeString(end) ?? quietHoursEnd
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadLocations() async {
        do {
            savedLocations = try await apiClient?.fetchSavedLocations() ?? []
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Save (Debounced)

    func debounceSavePreferences() {
        saveTask?.cancel()
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms debounce
            guard !Task.isCancelled else { return }
            await savePreferences()
        }
    }

    private func savePreferences() async {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"

        let update = UpdateUserRequest(
            defaultBufferMinutes: defaultBufferMinutes,
            defaultTravelMode: defaultTravelMode.rawValue,
            quietHoursStart: quietHoursEnabled ? formatter.string(from: quietHoursStart) : nil,
            quietHoursEnd: quietHoursEnabled ? formatter.string(from: quietHoursEnd) : nil
        )

        do {
            _ = try await apiClient?.updateProfile(update)
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Locations

    func deleteLocation(_ location: SavedLocation) async {
        do {
            try await apiClient?.deleteSavedLocation(locationId: location.id)
            savedLocations.removeAll { $0.id == location.id }
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: - Private

    private func parseTimeString(_ time: String) -> Date? {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.date(from: time)
    }
}

// MARK: - TravelMode Icon

extension TravelMode {
    var icon: String {
        switch self {
        case .driving: return "car.fill"
        case .transit: return "bus.fill"
        case .walking: return "figure.walk"
        case .cycling: return "bicycle"
        }
    }
}
