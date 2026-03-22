import Foundation
import SwiftUI

/// ViewModel for the home dashboard.
@Observable
final class HomeViewModel {
    // Trip data
    var nextDeparture: Trip?
    var laterToday: [Trip] = []
    var tomorrow: [Trip] = []

    // UI state
    var isLoading = false
    var error: String?

    // Dependencies
    private var apiClient: APIClient?

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Load Trips

    func loadTrips() async {
        isLoading = true
        error = nil

        do {
            let trips = try await apiClient?.fetchUpcomingTrips() ?? []
            groupTrips(trips)
        } catch let apiError as APIError {
            error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Group Trips

    private func groupTrips(_ trips: [Trip]) {
        let calendar = Calendar.current
        let now = Date()

        // Sort by notify_at (departure time) or arrival_time
        let sorted = trips
            .filter { $0.statusEnum != .completed && $0.statusEnum != .cancelled }
            .sorted { ($0.notifyAt ?? $0.arrivalTime) < ($1.notifyAt ?? $1.arrivalTime) }

        // Next departure: the first trip that hasn't departed yet
        nextDeparture = sorted.first

        // Later today: remaining trips today (excluding next departure)
        let todayTrips = sorted.filter { calendar.isDateInToday($0.arrivalTime) }
        laterToday = Array(todayTrips.dropFirst())

        // Tomorrow
        tomorrow = sorted.filter { calendar.isDateInTomorrow($0.arrivalTime) }
    }

    // MARK: - Actions

    func deleteTrip(_ trip: Trip) async {
        do {
            try await apiClient?.deleteTrip(tripId: trip.id)
            await loadTrips()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
