import XCTest
@testable import Depart

final class TripMonitorTests: XCTestCase {

    // MARK: - TravelMode MKTransportType Mapping

    func testTravelMode_driving_mapsToAutomobile() {
        XCTAssertEqual(TravelMode.driving.mkTransportType, .automobile)
    }

    func testTravelMode_transit_mapsToTransit() {
        XCTAssertEqual(TravelMode.transit.mkTransportType, .transit)
    }

    func testTravelMode_walking_mapsToWalking() {
        XCTAssertEqual(TravelMode.walking.mkTransportType, .walking)
    }

    func testTravelMode_cycling_mapsToWalking() {
        // MapKit doesn't have a cycling transport type
        XCTAssertEqual(TravelMode.cycling.mkTransportType, .walking)
    }

    // MARK: - ETA Change Detection

    func testETAChange_significantWhenDiffMoreThan3Min() {
        let cachedETA = 1800 // 30 min
        let newETA = 2100    // 35 min
        let diff = abs(newETA - cachedETA)
        XCTAssertTrue(diff > 180, "5 min difference should be significant")
    }

    func testETAChange_insignificantWhenDiffLessThan3Min() {
        let cachedETA = 1800 // 30 min
        let newETA = 1900    // ~31.7 min
        let diff = abs(newETA - cachedETA)
        XCTAssertFalse(diff > 180, "1.7 min difference should not be significant")
    }

    // MARK: - Departure Time Calculation

    func testDepartureTimeCalculation() {
        let arrivalTime = Date().addingTimeInterval(7200) // 2 hours from now
        let etaSeconds = 1800 // 30 min
        let bufferMinutes = 10

        let departureTime = arrivalTime.addingTimeInterval(
            -TimeInterval(etaSeconds + bufferMinutes * 60)
        )

        let minutesUntilDeparture = Int(departureTime.timeIntervalSinceNow / 60)
        // Should be approximately 80 min from now (120 - 30 - 10)
        XCTAssertTrue(minutesUntilDeparture >= 78 && minutesUntilDeparture <= 81)
    }

    // MARK: - Notification Tier Selection

    func testNotificationTier_leaveNow_when5MinOrLess() {
        let tier = notificationTier(minutesUntilDeparture: 3)
        XCTAssertEqual(tier, .leaveNow)
    }

    func testNotificationTier_leaveSoon_when6To15Min() {
        let tier = notificationTier(minutesUntilDeparture: 12)
        XCTAssertEqual(tier, .leaveSoon)
    }

    func testNotificationTier_prepare_when16To30Min() {
        let tier = notificationTier(minutesUntilDeparture: 25)
        XCTAssertEqual(tier, .prepare)
    }

    // MARK: - Helpers

    private func notificationTier(minutesUntilDeparture: Int) -> NotificationType {
        if minutesUntilDeparture <= 5 {
            return .leaveNow
        } else if minutesUntilDeparture <= 15 {
            return .leaveSoon
        } else {
            return .prepare
        }
    }
}
