import Foundation

/// Matches backend `app/models/enums.py` NotificationType exactly.
enum NotificationType: String, Codable {
    case headsUp = "heads_up"
    case prepare = "prepare"
    case leaveSoon = "leave_soon"
    case leaveNow = "leave_now"
    case runningLate = "running_late"

    var displayName: String {
        switch self {
        case .headsUp: return "Heads Up"
        case .prepare: return "Prepare"
        case .leaveSoon: return "Leave Soon"
        case .leaveNow: return "Leave Now"
        case .runningLate: return "Running Late"
        }
    }

    var isUrgent: Bool {
        self == .leaveSoon || self == .leaveNow || self == .runningLate
    }
}

/// Matches backend `app/models/enums.py` DeliveryStatus exactly.
enum DeliveryStatus: String, Codable {
    case pending
    case delivered
    case failed
    case dismissed
    case tapped
}

/// Matches backend `app/schemas/trip.py` NotificationResponse exactly.
struct NotificationLogEntry: Identifiable, Codable {
    let id: UUID
    let sentAt: Date
    let type: String
    let title: String
    let body: String
    let etaAtSendSeconds: Int?
    let recommendedDeparture: Date?
    let deliveryStatus: String
}

extension NotificationLogEntry {
    var typeEnum: NotificationType {
        NotificationType(rawValue: type) ?? .headsUp
    }

    var deliveryStatusEnum: DeliveryStatus {
        DeliveryStatus(rawValue: deliveryStatus) ?? .pending
    }
}
