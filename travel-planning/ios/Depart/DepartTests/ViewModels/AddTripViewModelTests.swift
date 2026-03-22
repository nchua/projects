import CoreLocation
import XCTest
@testable import Depart

final class AddTripViewModelTests: XCTestCase {

    // MARK: - Validation

    func testIsValid_false_whenNoDestination() {
        let vm = AddTripViewModel()
        vm.origin = makeLocationResult(name: "Home")
        vm.destination = nil
        vm.arrivalDate = Date().addingTimeInterval(3600)
        XCTAssertFalse(vm.isValid)
    }

    func testIsValid_false_whenNoOrigin() {
        let vm = AddTripViewModel()
        vm.origin = nil
        vm.destination = makeLocationResult(name: "Work")
        vm.arrivalDate = Date().addingTimeInterval(3600)
        XCTAssertFalse(vm.isValid)
    }

    func testIsValid_false_whenArrivalInPast() {
        let vm = AddTripViewModel()
        vm.origin = makeLocationResult(name: "Home")
        vm.destination = makeLocationResult(name: "Work")
        vm.arrivalDate = Date().addingTimeInterval(-3600) // 1 hour ago
        XCTAssertFalse(vm.isValid)
    }

    func testIsValid_true_whenAllFieldsSet() {
        let vm = AddTripViewModel()
        vm.origin = makeLocationResult(name: "Home")
        vm.destination = makeLocationResult(name: "Work")
        vm.arrivalDate = Date().addingTimeInterval(3600) // 1 hour from now
        XCTAssertTrue(vm.isValid)
    }

    // MARK: - Trip Name

    func testTripName_usesCustomName_whenProvided() {
        let vm = AddTripViewModel()
        vm.name = "Morning Commute"
        vm.destination = makeLocationResult(name: "Office")
        XCTAssertEqual(vm.tripName, "Morning Commute")
    }

    func testTripName_usesDestinationName_whenNoCustomName() {
        let vm = AddTripViewModel()
        vm.name = ""
        vm.destination = makeLocationResult(name: "Office")
        XCTAssertEqual(vm.tripName, "Office")
    }

    func testTripName_usesDefault_whenNoNameOrDestination() {
        let vm = AddTripViewModel()
        vm.name = ""
        vm.destination = nil
        XCTAssertEqual(vm.tripName, "New Trip")
    }

    // MARK: - Buffer

    func testBufferMinutes_defaultIs15() {
        let vm = AddTripViewModel()
        XCTAssertEqual(vm.bufferMinutes, 15)
    }

    // MARK: - Helpers

    private func makeLocationResult(name: String) -> LocationResult {
        LocationResult(
            name: name,
            address: "123 \(name) St, San Francisco, CA",
            coordinate: CLLocationCoordinate2D(latitude: 37.7749, longitude: -122.4194)
        )
    }
}
