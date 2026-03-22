import XCTest
@testable import Depart

final class TripDetailViewModelTests: XCTestCase {

    // MARK: - Initial State

    func testInitialState_isNil() {
        let vm = TripDetailViewModel()
        XCTAssertNil(vm.trip)
        XCTAssertTrue(vm.notifications.isEmpty)
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
    }

    // MARK: - Countdown Logic

    func testCountdown_minutesUntilDeparture_positive() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(45 * 60) // 45 min from now
        XCTAssertNotNil(trip.minutesUntilDeparture)
        let minutes = trip.minutesUntilDeparture!
        XCTAssertTrue(minutes >= 44 && minutes <= 45)
    }

    func testCountdown_minutesUntilDeparture_overdue() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(-15 * 60) // 15 min ago
        XCTAssertNotNil(trip.minutesUntilDeparture)
        let minutes = trip.minutesUntilDeparture!
        XCTAssertTrue(minutes < 0)
    }

    // MARK: - Urgency Color Mapping

    func testUrgency_normalAbove30() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(60 * 60)
        XCTAssertEqual(trip.urgencyLevel, .normal)
    }

    func testUrgency_warningBetween10And30() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(15 * 60)
        XCTAssertEqual(trip.urgencyLevel, .warning)
    }

    func testUrgency_criticalBelow10() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(5 * 60)
        XCTAssertEqual(trip.urgencyLevel, .critical)
    }

    func testUrgency_overdueWhenNegative() {
        var trip = makeTrip()
        trip.notifyAt = Date().addingTimeInterval(-5 * 60)
        XCTAssertEqual(trip.urgencyLevel, .overdue)
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
            destAddress: "Office",
            destLat: 37.7849,
            destLng: -122.4094,
            destLocationId: nil,
            arrivalTime: Date().addingTimeInterval(7200),
            travelMode: "driving",
            bufferMinutes: 10,
            status: "monitoring",
            monitoringStartedAt: Date(),
            lastEtaSeconds: 1800,
            lastCheckedAt: Date(),
            notifyAt: Date().addingTimeInterval(3600),
            baselineDurationSeconds: 1800,
            notified: false,
            notificationCount: 0,
            isRecurring: false,
            recurrenceRule: nil,
            calendarEventId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}
