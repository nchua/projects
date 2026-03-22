import Foundation

extension Date {
    /// "10:23 AM" format
    var shortTimeString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: self)
    }

    /// "42 min" or "1 hr 12 min" relative countdown
    static func countdownString(minutes: Int) -> String {
        if minutes < 0 {
            let absMin = abs(minutes)
            if absMin >= 60 {
                return "\(absMin / 60) hr \(absMin % 60) min late"
            }
            return "\(absMin) min late"
        }
        if minutes >= 60 {
            let hrs = minutes / 60
            let mins = minutes % 60
            if mins == 0 { return "\(hrs) hr" }
            return "\(hrs) hr \(mins) min"
        }
        return "\(minutes) min"
    }

    /// "Today", "Tomorrow", or "Mar 22"
    var relativeDayString: String {
        if Calendar.current.isDateInToday(self) { return "Today" }
        if Calendar.current.isDateInTomorrow(self) { return "Tomorrow" }
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return formatter.string(from: self)
    }

    /// "Mar 22, 10:23 AM"
    var mediumDateTimeString: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, h:mm a"
        return formatter.string(from: self)
    }
}
