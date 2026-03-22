import BackgroundTasks
import Foundation
import MapKit

/// Background app refresh task that checks ETAs for active trips
/// and schedules local notifications as a server-push failsafe.
@Observable
final class TripMonitor {
    static let shared = TripMonitor()
    static let taskIdentifier = "com.depart.trip-eta-refresh"

    private let persistence = PersistenceController.shared

    // MARK: - BGTask Registration

    /// Register the background task identifier. Call from AppDelegate.didFinishLaunching.
    func registerBackgroundTask() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.taskIdentifier,
            using: nil
        ) { [weak self] task in
            guard let bgTask = task as? BGAppRefreshTask else { return }
            self?.handleAppRefresh(task: bgTask)
        }
    }

    /// Schedule the next background app refresh.
    func scheduleAppRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: Self.taskIdentifier)
        // Request refresh in 15 minutes (system may delay further)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)

        do {
            try BGTaskScheduler.shared.submit(request)
            print("[TripMonitor] Scheduled background refresh")
        } catch {
            print("[TripMonitor] Failed to schedule refresh: \(error)")
        }
    }

    // MARK: - Background Refresh Handler

    private func handleAppRefresh(task: BGAppRefreshTask) {
        // Schedule the next refresh before starting work
        scheduleAppRefresh()

        let workTask = Task {
            await checkActiveTrips()
        }

        task.expirationHandler = {
            workTask.cancel()
        }

        Task {
            _ = await workTask.result
            task.setTaskCompleted(success: true)
        }
    }

    /// Check ETA for all active/monitoring trips using on-device MKDirections.
    @MainActor
    func checkActiveTrips() async {
        let trips = persistence.fetchCachedTrips()
        let activeTrips = trips.filter {
            $0.statusEnum == .monitoring || $0.statusEnum == .pending
        }

        guard !activeTrips.isEmpty else { return }
        print("[TripMonitor] Checking \(activeTrips.count) active trips")

        for trip in activeTrips {
            await checkTripETA(trip)
        }
    }

    // MARK: - ETA Check

    private func checkTripETA(_ trip: Trip) async {
        let origin = MKMapItem(placemark: MKPlacemark(
            coordinate: CLLocationCoordinate2D(latitude: trip.originLat, longitude: trip.originLng)
        ))
        let destination = MKMapItem(placemark: MKPlacemark(
            coordinate: CLLocationCoordinate2D(latitude: trip.destLat, longitude: trip.destLng)
        ))

        let request = MKDirections.Request()
        request.source = origin
        request.destination = destination
        request.transportType = trip.travelModeEnum.mkTransportType

        do {
            let directions = MKDirections(request: request)
            let eta = try await directions.calculateETA()
            let newETASeconds = Int(eta.expectedTravelTime)

            // Compare with cached ETA
            let cachedETA = trip.lastEtaSeconds ?? 0
            let difference = abs(newETASeconds - cachedETA)

            // If ETA differs by more than 3 minutes, schedule updated local notification
            if difference > 180 {
                let departureTime = trip.arrivalTime.addingTimeInterval(
                    -TimeInterval(newETASeconds + trip.bufferMinutes * 60)
                )
                let minutesUntilDeparture = Int(departureTime.timeIntervalSinceNow / 60)

                if minutesUntilDeparture <= 30 && minutesUntilDeparture > 0 {
                    let tier: NotificationType
                    if minutesUntilDeparture <= 5 {
                        tier = .leaveNow
                    } else if minutesUntilDeparture <= 15 {
                        tier = .leaveSoon
                    } else {
                        tier = .prepare
                    }

                    await NotificationManager.shared.scheduleLocalNotification(
                        tripId: trip.id,
                        title: tier == .leaveNow ? "Time to leave!" : "Traffic update",
                        body: "ETA now \(newETASeconds / 60) min. Leave by \(departureTime.shortTimeString) to arrive on time.",
                        fireDate: Date().addingTimeInterval(5), // Fire in 5 seconds
                        tier: tier
                    )
                }

                print("[TripMonitor] ETA changed for \(trip.name): \(cachedETA/60) -> \(newETASeconds/60) min")
            }
        } catch {
            print("[TripMonitor] ETA check failed for \(trip.name): \(error)")
        }
    }
}

// MARK: - TravelMode MKDirections Extension

extension TravelMode {
    var mkTransportType: MKDirectionsTransportType {
        switch self {
        case .driving: return .automobile
        case .transit: return .transit
        case .walking: return .walking
        case .cycling: return .walking // MapKit doesn't have cycling
        }
    }
}
