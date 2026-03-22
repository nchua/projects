import XCTest
@testable import Depart

final class TripTests: XCTestCase {

    // MARK: - Urgency Level

    func testUrgencyLevel_normal_when_moreThan30Min() {
        let trip = makeTripWithDeparture(minutesFromNow: 45)
        XCTAssertEqual(trip.urgencyLevel, .normal)
    }

    func testUrgencyLevel_warning_when_10to30Min() {
        let trip = makeTripWithDeparture(minutesFromNow: 20)
        XCTAssertEqual(trip.urgencyLevel, .warning)
    }

    func testUrgencyLevel_critical_when_lessThan10Min() {
        let trip = makeTripWithDeparture(minutesFromNow: 5)
        XCTAssertEqual(trip.urgencyLevel, .critical)
    }

    func testUrgencyLevel_overdue_when_negative() {
        let trip = makeTripWithDeparture(minutesFromNow: -5)
        XCTAssertEqual(trip.urgencyLevel, .overdue)
    }

    func testUrgencyLevel_normal_when_noDepartureTime() {
        let trip = makeTripWithDeparture(minutesFromNow: nil)
        XCTAssertEqual(trip.urgencyLevel, .normal)
    }

    // MARK: - Computed Properties

    func testEstimatedTravelMinutes() {
        var trip = makeTrip()
        trip.lastEtaSeconds = 1800 // 30 minutes
        XCTAssertEqual(trip.estimatedTravelMinutes, 30)
    }

    func testEstimatedTravelMinutes_nil_whenNoETA() {
        var trip = makeTrip()
        trip.lastEtaSeconds = nil
        XCTAssertNil(trip.estimatedTravelMinutes)
    }

    func testTravelModeEnum_defaultsToDriving() {
        var trip = makeTrip()
        trip.travelMode = "unknown_mode"
        XCTAssertEqual(trip.travelModeEnum, .driving)
    }

    func testStatusEnum_defaultsToPending() {
        var trip = makeTrip()
        trip.status = "unknown_status"
        XCTAssertEqual(trip.statusEnum, .pending)
    }

    func testDepartureTime_isNotifyAt() {
        var trip = makeTrip()
        let expected = Date().addingTimeInterval(3600)
        trip.notifyAt = expected
        XCTAssertEqual(trip.departureTime, expected)
    }

    // MARK: - AnyCodableValue

    func testAnyCodableValue_roundTrip_string() throws {
        let value = AnyCodableValue.string("test")
        let data = try JSONEncoder().encode(value)
        let decoded = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        XCTAssertEqual(decoded, value)
    }

    func testAnyCodableValue_roundTrip_dictionary() throws {
        let value = AnyCodableValue.dictionary([
            "days": .array([.string("mon"), .string("wed")]),
            "interval": .int(1),
        ])
        let data = try JSONEncoder().encode(value)
        let decoded = try JSONDecoder().decode(AnyCodableValue.self, from: data)
        XCTAssertEqual(decoded, value)
    }

    // MARK: - Helpers

    private func makeTrip() -> Trip {
        Trip(
            id: UUID(),
            name: "Test Trip",
            originAddress: "Home",
            originLat: 37.7749,
            originLng: -122.4194,
            originLocationId: nil,
            originIsCurrentLocation: false,
            destAddress: "Work",
            destLat: 37.7849,
            destLng: -122.4094,
            destLocationId: nil,
            arrivalTime: Date().addingTimeInterval(7200),
            travelMode: "driving",
            bufferMinutes: 10,
            status: "pending",
            monitoringStartedAt: nil,
            lastEtaSeconds: nil,
            lastCheckedAt: nil,
            notifyAt: nil,
            baselineDurationSeconds: nil,
            notified: false,
            notificationCount: 0,
            isRecurring: false,
            recurrenceRule: nil,
            calendarEventId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }

    private func makeTripWithDeparture(minutesFromNow: Int?) -> Trip {
        var trip = makeTrip()
        if let minutes = minutesFromNow {
            trip.notifyAt = Date().addingTimeInterval(TimeInterval(minutes * 60))
        } else {
            trip.notifyAt = nil
        }
        return trip
    }
}

// Equatable for testing
extension Trip.UrgencyLevel: Equatable {}
