import XCTest

/// M6: the in-app camera. In the simulator there is no camera, so the screen must say so and go back cleanly.
/// On a device the test grants camera access, presses the shutter, waits for the capture to be written and
/// then for it to develop in the list.
final class CameraFlowTests: XCTestCase {
    func testCameraScreen() throws {
        let app = XCUIApplication()
        app.launch()
        app.buttons["Take Photo"].firstMatch.tap()

        // The controls exist only once the session runs, so the shutter is a true readiness signal; the
        // unavailable screen carries its reason. The camera permission alert (device, first run) is Springboard's.
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let shutter = app.buttons["Shutter"]
        let unavailable = app.staticTexts["camera-unavailable-reason"]
        let deadline = Date().addingTimeInterval(30)
        while Date() < deadline, !shutter.exists, !unavailable.exists {
            let allow = springboard.buttons["Allow"]
            if allow.exists { allow.tap() }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        add(XCTAttachment(screenshot: app.screenshot()))
        if unavailable.exists {
            let reason = unavailable.label
            app.buttons["Done"].tap()
            XCTAssertTrue(app.buttons["Take Photo"].firstMatch.waitForExistence(timeout: 5), "didn't return to the list")
            if reason == "No camera on this device" { throw XCTSkip("no camera in the simulator; the capture path needs a device") }
            return XCTFail("camera unavailable: \(reason)")
        }
        XCTAssertTrue(shutter.exists, "the camera didn't become ready in 30 s")
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH 'ProRAW'")).firstMatch.exists,
                      "the viewfinder doesn't show a ProRAW format")

        // The shutter disables while the capture is in flight and comes back once the DNG is written and queued
        shutter.tap()
        expectation(for: NSPredicate(format: "isEnabled == true"), evaluatedWith: shutter)
        waitForExpectations(timeout: 30)
        add(XCTAttachment(screenshot: app.screenshot()))
        app.buttons["Done"].tap()

        // The capture develops like a picked photo (Debug rows show the timings)
        let rendered = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'decode'")).firstMatch
        let skipped = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'skipped'")).firstMatch
        XCTAssertTrue(rendered.waitForExistence(timeout: 90), skipped.exists ? skipped.label : "the capture didn't develop")
        print("CAPTURE ROW: \(rendered.label)")
        add(XCTAttachment(screenshot: app.screenshot()))
    }
}
