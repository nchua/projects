import Foundation
import MapKit

/// ViewModel for the trip detail screen.
@Observable
final class TripDetailViewModel {
    var trip: Trip?
    var etaSnapshots: [EtaSnapshot] = []
    var notifications: [NotificationLogEntry] = []
    var route: MKRoute?
    var isLoading = false
    var error: String?

    private var apiClient: APIClient?

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Load Detail

    func loadDetail(tripId: UUID) async {
        isLoading = true
        error = nil

        do {
            let detail = try await apiClient?.fetchTripDetail(tripId: tripId)
            if let detail {
                trip = detail.asTrip
                etaSnapshots = detail.etaSnapshots
                notifications = detail.notifications
            }
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Actions

    /// Open destination in preferred maps app.
    func openInMaps() {
        guard let trip else { return }

        let coordinate = CLLocationCoordinate2D(
            latitude: trip.destLat,
            longitude: trip.destLng
        )
        let placemark = MKPlacemark(coordinate: coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = trip.name

        mapItem.openInMaps(launchOptions: [
            MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving,
        ])
    }

    /// Snooze trip by 10 minutes (push arrival time forward).
    func snoozeTenMinutes() async {
        guard let trip, let apiClient else { return }

        do {
            let updated = try await apiClient.snoozeTrip(
                tripId: trip.id,
                minutes: 10,
                currentArrivalTime: trip.arrivalTime
            )
            self.trip = updated
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Mark trip as departed, stop monitoring.
    func markDeparted() async {
        guard let trip, let apiClient else { return }

        do {
            let updated = try await apiClient.markDeparted(tripId: trip.id)
            self.trip = updated
            NotificationManager.shared.cancelNotifications(for: trip.id)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
