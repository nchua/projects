import Foundation
import SwiftUI

@MainActor
final class WeeklyReportViewModel: ObservableObject {
    @Published var report: WeeklyProgressReportResponse?
    @Published var isLoading = false
    @Published var error: String?

    var weekDateRange: String {
        guard let report else { return "" }
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"

        let start = report.weekStart.parseISO8601Date()
        let end = report.weekEnd.parseISO8601Date()
        switch (start, end) {
        case let (s?, e?):
            return "\(formatter.string(from: s)) - \(formatter.string(from: e))"
        case let (s?, nil):
            return formatter.string(from: s)
        case let (nil, e?):
            return formatter.string(from: e)
        default:
            return ""
        }
    }

    var volumeFormatted: String {
        guard let report else { return "0" }
        let value = report.totalVolume
        if value >= 1000 {
            return String(format: "%.1fk", value / 1000.0)
        }
        return String(format: "%.0f", value)
    }

    var status: String {
        guard let report, !report.goalReports.isEmpty else { return "on_track" }
        if report.goalReports.contains(where: { $0.status == "behind" }) { return "behind" }
        if report.goalReports.contains(where: { $0.status == "ahead" }) { return "ahead" }
        return "on_track"
    }

    var statusLabel: String {
        switch status {
        case "ahead":
            return "AHEAD"
        case "behind":
            return "BEHIND"
        default:
            return "ON TRACK"
        }
    }

    var statusColor: Color {
        switch status {
        case "ahead":
            return .gold
        case "behind":
            return .warningRed
        default:
            return .systemPrimary
        }
    }

    var volumeChangeFormatted: String? {
        guard let change = report?.volumeChangePercent else { return nil }
        return String(format: "%@%.0f%%", change >= 0 ? "+" : "", change)
    }

    func loadReport() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            report = try await APIClient.shared.getWeeklyProgressReport()
        } catch let apiError as APIError {
            error = apiError.localizedDescription
        } catch {
            self.error = error.localizedDescription
        }
    }
}
