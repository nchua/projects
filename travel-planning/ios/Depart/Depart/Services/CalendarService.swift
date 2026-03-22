import EventKit
import Foundation

/// EventKit wrapper for calendar integration.
/// Fetches events with locations and creates monitored trips from them.
@Observable
final class CalendarService {
    static let shared = CalendarService()

    private let store = EKEventStore()

    var authorizationStatus: EKAuthorizationStatus {
        EKEventStore.authorizationStatus(for: .event)
    }

    var isAuthorized: Bool {
        authorizationStatus == .fullAccess || authorizationStatus == .authorized
    }

    var calendars: [EKCalendar] {
        guard isAuthorized else { return [] }
        return store.calendars(for: .event)
    }

    // MARK: - Authorization

    /// Request calendar access (iOS 17+ uses full access).
    func requestAccess() async -> Bool {
        do {
            let granted = try await store.requestFullAccessToEvents()
            return granted
        } catch {
            print("[CalendarService] Access error: \(error)")
            return false
        }
    }

    // MARK: - Fetch Events

    /// Fetch upcoming events that have a location string.
    func fetchEventsWithLocations(
        from startDate: Date = Date(),
        to endDate: Date? = nil,
        calendarIds: Set<String>? = nil
    ) -> [EKEvent] {
        guard isAuthorized else { return [] }

        let end = endDate ?? Calendar.current.date(byAdding: .day, value: 7, to: startDate)!
        let predicate = store.predicateForEvents(
            withStart: startDate,
            end: end,
            calendars: filteredCalendars(ids: calendarIds)
        )

        return store.events(matching: predicate)
            .filter { event in
                guard let location = event.location, !location.isEmpty else { return false }
                // Filter out virtual meeting links
                let lowered = location.lowercased()
                return !lowered.contains("zoom.us") &&
                    !lowered.contains("meet.google") &&
                    !lowered.contains("teams.microsoft")
            }
    }

    /// Create trip requests from calendar events by geocoding their locations.
    func createTripsFromEvents(
        _ events: [EKEvent],
        apiClient: APIClient,
        defaultOrigin: SavedLocation?
    ) async -> [Trip] {
        var created: [Trip] = []
        let geocoder = CLGeocoder()

        for event in events {
            guard let locationString = event.location else { continue }

            do {
                let placemarks = try await geocoder.geocodeAddressString(locationString)
                guard let placemark = placemarks.first,
                      let coordinate = placemark.location?.coordinate
                else { continue }

                let request = CreateTripRequest(
                    name: event.title ?? "Calendar Event",
                    originAddress: defaultOrigin?.address,
                    originLat: defaultOrigin?.latitude,
                    originLng: defaultOrigin?.longitude,
                    originLocationId: defaultOrigin?.id,
                    originIsCurrentLocation: defaultOrigin == nil,
                    destAddress: placemark.formattedAddress ?? locationString,
                    destLat: coordinate.latitude,
                    destLng: coordinate.longitude,
                    destLocationId: nil,
                    arrivalTime: event.startDate,
                    travelMode: nil,
                    bufferMinutes: nil,
                    isRecurring: false,
                    recurrenceRule: nil,
                    calendarEventId: event.eventIdentifier
                )

                let trip = try await apiClient.createTrip(request)
                created.append(trip)
            } catch {
                print("[CalendarService] Failed to create trip for '\(event.title ?? "")': \(error)")
            }
        }

        return created
    }

    // MARK: - Private

    private func filteredCalendars(ids: Set<String>?) -> [EKCalendar]? {
        guard let ids, !ids.isEmpty else { return nil }
        return store.calendars(for: .event).filter { ids.contains($0.calendarIdentifier) }
    }
}

// MARK: - CLGeocoder

import CoreLocation

private extension CLPlacemark {
    var formattedAddress: String? {
        [subThoroughfare, thoroughfare, locality, administrativeArea]
            .compactMap { $0 }
            .joined(separator: " ")
            .nilIfEmpty
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
