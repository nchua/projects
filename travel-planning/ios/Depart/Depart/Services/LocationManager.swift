import CoreLocation
import MapKit
import SwiftUI

/// CLLocationManager wrapper for "When In Use" location services.
@Observable
final class LocationManager: NSObject, CLLocationManagerDelegate {
    var currentLocation: CLLocation?
    var authorizationStatus: CLAuthorizationStatus = .notDetermined
    var currentPlacemark: CLPlacemark?

    private let locationManager = CLLocationManager()
    private let geocoder = CLGeocoder()

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        authorizationStatus = locationManager.authorizationStatus
    }

    // MARK: - Authorization

    func requestWhenInUseAuthorization() {
        locationManager.requestWhenInUseAuthorization()
    }

    // MARK: - Current Location

    /// One-shot location request (battery friendly).
    func requestCurrentLocation() {
        locationManager.requestLocation()
    }

    // MARK: - Geocoding

    func reverseGeocode(location: CLLocation) async throws -> CLPlacemark {
        let placemarks = try await geocoder.reverseGeocodeLocation(location)
        guard let placemark = placemarks.first else {
            throw LocationError.geocodingFailed
        }
        return placemark
    }

    func forwardGeocode(address: String) async throws -> CLPlacemark {
        let placemarks = try await geocoder.geocodeAddressString(address)
        guard let placemark = placemarks.first else {
            throw LocationError.geocodingFailed
        }
        return placemark
    }

    // MARK: - CLLocationManagerDelegate

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        currentLocation = location
        Task {
            currentPlacemark = try? await reverseGeocode(location: location)
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("[LocationManager] Error: \(error.localizedDescription)")
    }

    // MARK: - Error

    enum LocationError: Error, LocalizedError {
        case geocodingFailed
        case notAuthorized

        var errorDescription: String? {
            switch self {
            case .geocodingFailed: return "Could not find that address."
            case .notAuthorized: return "Location access is required."
            }
        }
    }
}
