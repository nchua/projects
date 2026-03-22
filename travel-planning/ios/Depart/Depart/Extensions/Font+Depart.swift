import SwiftUI

extension Font {
    // MARK: - Typography from UX Spec

    /// 48px weight 800 — Countdown ring center number
    static let departCountdown = Font.system(size: 48, weight: .heavy, design: .rounded)

    /// 42px weight 800 — Leave-by time on hero card
    static let departHeroTime = Font.system(size: 42, weight: .heavy, design: .rounded)

    /// 34px weight 800 — Screen headers
    static let departLargeTitle = Font.system(size: 34, weight: .heavy)

    /// 28px weight 800 — Trip detail header, onboarding titles
    static let departTitle1 = Font.system(size: 28, weight: .heavy)

    /// 22px weight 700 — Hero card event name
    static let departTitle2 = Font.system(size: 22, weight: .bold)

    /// 20px weight 700 — Section titles
    static let departTitle3 = Font.system(size: 20, weight: .bold)

    /// 17px weight 600 — Nav titles, setting labels
    static let departHeadline = Font.system(size: 17, weight: .semibold)

    /// 16px weight 500 — Trip names, input values
    static let departBody = Font.system(size: 16, weight: .medium)

    /// 15px weight 500 — Destination text, trip meta
    static let departCallout = Font.system(size: 15, weight: .medium)

    /// 14px weight 500 — Supporting text, banner body
    static let departSubhead = Font.system(size: 14, weight: .medium)

    /// 13px weight 600 — Labels, timestamps, descriptions
    static let departCaption = Font.system(size: 13, weight: .semibold)

    /// 12px weight 600 — Section titles (uppercase), small labels
    static let departCaption2 = Font.system(size: 12, weight: .semibold)

    /// 11px weight 600 — Countdown labels, widget units
    static let departOverline = Font.system(size: 11, weight: .semibold)
}
