import Foundation
import MapKit
import SwiftUI

/// ViewModel for the Add Trip form.
@Observable
final class AddTripViewModel {
    // Form state
    var name = ""
    var origin: LocationResult?
    var destination: LocationResult?
    var arrivalDate = Date().addingTimeInterval(3600) // 1 hour from now
    var bufferMinutes = 15

    // UI state
    var isSaving = false
    var error: String?
    var routeEstimateMinutes: Int?
    var showOriginSearch = false
    var showDestSearch = false

    // Dependencies
    private var apiClient: APIClient?
    private var savedLocations: [SavedLocation] = []

    func configure(apiClient: APIClient, savedLocations: [SavedLocation]) {
        self.apiClient = apiClient
        self.savedLocations = savedLocations

        // Default origin to Home if available
        if let home = savedLocations.first(where: { $0.name.lowercased() == "home" }) {
            origin = LocationResult(
                name: home.name,
                address: home.address,
                coordinate: CLLocationCoordinate2D(
                    latitude: home.latitude,
                    longitude: home.longitude
                )
            )
        }
    }

    // MARK: - Validation

    var isValid: Bool {
        destination != nil
            && arrivalDate > Date()
            && (origin != nil)
    }

    var tripName: String {
        if !name.isEmpty { return name }
        return destination?.name ?? "New Trip"
    }

    // MARK: - Route Estimation

    /// Estimate route using on-device MKDirections (free, no backend needed).
    func estimateRoute() async {
        guard let origin, let destination else {
            routeEstimateMinutes = nil
            return
        }

        let request = MKDirections.Request()
        request.source = MKMapItem(placemark: MKPlacemark(coordinate: origin.coordinate))
        request.destination = MKMapItem(placemark: MKPlacemark(coordinate: destination.coordinate))
        request.transportType = .automobile

        do {
            let eta = try await MKDirections(request: request).calculateETA()
            routeEstimateMinutes = Int(eta.expectedTravelTime / 60)
        } catch {
            print("[AddTripVM] Route estimate error: \(error)")
            routeEstimateMinutes = nil
        }
    }

    // MARK: - Save

    func saveTrip() async -> Bool {
        guard isValid, let destination, let origin else { return false }

        isSaving = true
        error = nil

        let request = CreateTripRequest(
            name: tripName,
            originAddress: origin.address,
            originLat: origin.coordinate.latitude,
            originLng: origin.coordinate.longitude,
            originLocationId: nil,
            originIsCurrentLocation: false,
            destAddress: destination.address,
            destLat: destination.coordinate.latitude,
            destLng: destination.coordinate.longitude,
            destLocationId: nil,
            arrivalTime: arrivalDate,
            travelMode: "driving",
            bufferMinutes: bufferMinutes,
            isRecurring: false,
            recurrenceRule: nil,
            calendarEventId: nil
        )

        do {
            _ = try await apiClient?.createTrip(request)
            isSaving = false
            return true
        } catch {
            self.error = error.localizedDescription
            isSaving = false
            return false
        }
    }
}
