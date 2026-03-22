import XCTest
@testable import Depart

final class APIClientTests: XCTestCase {

    // MARK: - Date Decoding

    func testDateDecoding_iso8601WithFractionalSeconds() throws {
        let json = """
        {"date": "2026-03-22T10:30:00.123456+00:00"}
        """
        struct Wrapper: Codable { let date: Date }
        let decoded = try DateCoding.decoder.decode(Wrapper.self, from: json.data(using: .utf8)!)
        let calendar = Calendar(identifier: .gregorian)
        var components = calendar.dateComponents(in: TimeZone(identifier: "UTC")!, from: decoded.date)
        XCTAssertEqual(components.year, 2026)
        XCTAssertEqual(components.month, 3)
        XCTAssertEqual(components.day, 22)
        XCTAssertEqual(components.hour, 10)
        XCTAssertEqual(components.minute, 30)
    }

    func testDateDecoding_iso8601WithoutFractionalSeconds() throws {
        let json = """
        {"date": "2026-03-22T10:30:00+00:00"}
        """
        struct Wrapper: Codable { let date: Date }
        let decoded = try DateCoding.decoder.decode(Wrapper.self, from: json.data(using: .utf8)!)
        XCTAssertNotNil(decoded.date)
    }

    func testDateDecoding_invalidDate_throws() {
        let json = """
        {"date": "not-a-date"}
        """
        struct Wrapper: Codable { let date: Date }
        XCTAssertThrowsError(try DateCoding.decoder.decode(Wrapper.self, from: json.data(using: .utf8)!))
    }

    // MARK: - Snake Case Key Decoding

    func testSnakeCaseDecoding_tripFields() throws {
        let json = """
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Work Commute",
            "origin_address": "Home",
            "origin_lat": 37.77,
            "origin_lng": -122.41,
            "origin_location_id": null,
            "origin_is_current_location": false,
            "dest_address": "Office",
            "dest_lat": 37.78,
            "dest_lng": -122.40,
            "dest_location_id": null,
            "arrival_time": "2026-03-22T09:00:00+00:00",
            "travel_mode": "driving",
            "buffer_minutes": 10,
            "status": "pending",
            "monitoring_started_at": null,
            "last_eta_seconds": 1800,
            "last_checked_at": null,
            "notify_at": null,
            "baseline_duration_seconds": null,
            "notified": false,
            "notification_count": 0,
            "is_recurring": false,
            "recurrence_rule": null,
            "calendar_event_id": null,
            "created_at": "2026-03-22T08:00:00+00:00",
            "updated_at": "2026-03-22T08:00:00+00:00"
        }
        """
        let trip = try DateCoding.decoder.decode(Trip.self, from: json.data(using: .utf8)!)
        XCTAssertEqual(trip.name, "Work Commute")
        XCTAssertEqual(trip.originAddress, "Home")
        XCTAssertEqual(trip.destAddress, "Office")
        XCTAssertEqual(trip.bufferMinutes, 10)
        XCTAssertEqual(trip.lastEtaSeconds, 1800)
        XCTAssertFalse(trip.originIsCurrentLocation)
    }

    // MARK: - Date Encoding

    func testDateEncoding_producesISO8601() throws {
        let date = Date(timeIntervalSince1970: 0)
        struct Wrapper: Codable { let date: Date }
        let data = try DateCoding.encoder.encode(Wrapper(date: date))
        let json = String(data: data, encoding: .utf8)!
        XCTAssertTrue(json.contains("1970-01-01"))
    }

    // MARK: - API Error

    func testAPIError_descriptions() {
        XCTAssertNotNil(APIError.unauthorized.errorDescription)
        XCTAssertNotNil(APIError.offline.errorDescription)
        XCTAssertNotNil(APIError.invalidURL.errorDescription)
        XCTAssertNotNil(APIError.unknown.errorDescription)
        XCTAssertNotNil(APIError.serverError(500, "Internal Server Error").errorDescription)
    }

    // MARK: - Endpoint Paths

    func testEndpoint_paths() {
        XCTAssertEqual(Endpoint.register.path, "/auth/register")
        XCTAssertEqual(Endpoint.login.path, "/auth/login")
        XCTAssertEqual(Endpoint.upcomingTrips.path, "/trips/upcoming")
        XCTAssertEqual(Endpoint.savedLocations.path, "/locations")

        let testId = UUID()
        XCTAssertEqual(Endpoint.tripDetail(testId).path, "/trips/\(testId)")
        XCTAssertEqual(Endpoint.savedLocation(testId).path, "/locations/\(testId)")
        XCTAssertEqual(Endpoint.updateSavedLocation(testId).path, "/locations/\(testId)")
        XCTAssertEqual(Endpoint.deleteSavedLocation(testId).path, "/locations/\(testId)")
    }

    func testEndpoint_methods() {
        XCTAssertEqual(Endpoint.register.method, .post)
        XCTAssertEqual(Endpoint.login.method, .post)
        XCTAssertEqual(Endpoint.trips.method, .get)
        XCTAssertEqual(Endpoint.createTrip.method, .post)
        XCTAssertEqual(Endpoint.deleteTrip(UUID()).method, .delete)
        XCTAssertEqual(Endpoint.updateProfile.method, .patch)
        XCTAssertEqual(Endpoint.savedLocation(UUID()).method, .get)
        XCTAssertEqual(Endpoint.updateSavedLocation(UUID()).method, .put)
        XCTAssertEqual(Endpoint.deleteSavedLocation(UUID()).method, .delete)
    }

    func testEndpoint_authRequirements() {
        XCTAssertFalse(Endpoint.register.requiresAuth)
        XCTAssertFalse(Endpoint.login.requiresAuth)
        XCTAssertFalse(Endpoint.refreshToken.requiresAuth)
        XCTAssertTrue(Endpoint.trips.requiresAuth)
        XCTAssertTrue(Endpoint.savedLocations.requiresAuth)
        XCTAssertTrue(Endpoint.registerDeviceToken.requiresAuth)
    }
}
