import Foundation
import SwiftUI

/// Display model for alert history entries.
struct AlertEntry: Identifiable {
    let id: UUID
    let tripId: UUID
    let tripName: String
    let title: String
    let body: String
    let sentAt: Date
    let type: NotificationType

    var tierColor: Color {
        switch type {
        case .headsUp: return .departGreen
        case .prepare: return .departYellow
        case .leaveSoon: return .departOrange
        case .leaveNow: return .departRed
        case .runningLate: return .departRed
        }
    }
}

/// ViewModel for the Alerts tab.
@Observable
final class AlertsViewModel {
    var entries: [AlertEntry] = []
    var isLoading = false
    var error: String?

    private var apiClient: APIClient?

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// Load notification history from all recent trips.
    func loadAlerts() async {
        isLoading = true
        error = nil

        do {
            // Fetch recent trips that have notifications
            let response = try await apiClient?.fetchTrips(limit: 20) ?? PaginatedTripResponse(items: [], total: 0, limit: 20, offset: 0)

            var allEntries: [AlertEntry] = []

            // For each trip, fetch detail to get notifications
            for trip in response.items {
                guard trip.notificationCount > 0 else { continue }
                do {
                    let detail = try await apiClient?.fetchTripDetail(tripId: trip.id)
                    let notifications = detail?.notifications ?? []
                    for notification in notifications {
                        allEntries.append(AlertEntry(
                            id: notification.id,
                            tripId: trip.id,
                            tripName: trip.name,
                            title: notification.title,
                            body: notification.body,
                            sentAt: notification.sentAt,
                            type: notification.typeEnum
                        ))
                    }
                } catch {
                    // Skip this trip's notifications on error
                    continue
                }
            }

            // Sort by most recent first
            entries = allEntries.sorted { $0.sentAt > $1.sentAt }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}
