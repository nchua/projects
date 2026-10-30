import XCTest

/// M3 in the simulator: the real system picker -> render -> viewer -> save. Needs IMG_2725.DNG in the
/// simulator's library (`xcrun simctl addmedia booted IMG_2725.DNG`, see APP_SPEC.md M3) and add-only
/// Photos access granted beforehand (`xcrun simctl privacy booted grant photos-add com.nickchua.print`).
/// UI check only: the simulator is never a parity source. Saving adds a render to the library, so a re-run needs
/// a fresh library: `xcrun simctl erase <sim>`, then addmedia + privacy grant again.
final class PickerFlowTests: XCTestCase {
    /// The picker runs out of process: its grid shows up in the accessibility dump, but queries can't resolve
    /// those elements, so picks are coordinate taps on the iPhone 17 Pro Max simulator's layout (first row:
    /// IMG_2725, the newest item, then a stock JPEG; Done top right). The dump check keeps them honest.
    static let tiles = [CGVector(dx: 72, dy: 369), CGVector(dx: 220, dy: 369)]
    static let pickerDone = CGVector(dx: 398, dy: 114)

    func testPickRenderViewSave() throws {
        let app = XCUIApplication()
        app.launch()
        app.buttons["Pick Photos"].tap()
        sleep(3)
        // Fail (not skip) when the layout or library isn't what the taps assume. Saved renders carry
        // IMG_2725's capture time, so after a Save they'd be indistinguishable from it: one tile only.
        let dump = app.debugDescription
        XCTAssertTrue(dump.contains("{{-0.0, 296.0}, {145.6, 145.7}}, identifier: 'PXGGridLayout-Info', label: 'Photo, October 29"),
                      "IMG_2725 isn't the first picker tile (layout changed, or add it with simctl addmedia)")
        XCTAssertEqual(dump.components(separatedBy: "identifier: 'PXGGridLayout-Info', label: 'Photo, October 29").count - 1, 1,
                       "the library has saved renders of IMG_2725; erase the simulator and re-add the DNG")
        if testRun?.hasSucceeded == false { return }
        let origin = app.coordinate(withNormalizedOffset: .zero)
        for tile in Self.tiles {
            origin.withOffset(tile).tap()
            sleep(1)
        }
        origin.withOffset(Self.pickerDone).tap()

        // The JPEG is skipped with the spec's message; the DNG renders (Debug rows show timings)
        let skipped = app.staticTexts["Not ProRAW (or edited in Photos) — skipped"]
        let rendered = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'decode'")).firstMatch
        XCTAssertTrue(rendered.waitForExistence(timeout: 90), "render didn't finish")
        XCTAssertTrue(skipped.waitForExistence(timeout: 5), "non-RAW item wasn't skipped")
        print("RENDER ROW: \(rendered.label)")
        add(XCTAttachment(screenshot: app.screenshot()))

        // Viewer: the comparison exists ("hold for Apple"); holding swaps the label
        rendered.tap()
        let hint = app.staticTexts["Print · hold for Apple"]
        XCTAssertTrue(hint.waitForExistence(timeout: 5))
        add(XCTAttachment(screenshot: app.screenshot()))
        app.buttons["Done"].tap()

        // Save (add-only access pre-granted), then the row shows the saved checkmark
        app.buttons["Save"].firstMatch.tap()
        let saved = app.images["checkmark.circle.fill"].firstMatch
        let failed = app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH 'Save failed'")).firstMatch
        XCTAssertTrue(saved.waitForExistence(timeout: 20), failed.exists ? failed.label : "save didn't finish")
        add(XCTAttachment(screenshot: app.screenshot()))
    }
}
