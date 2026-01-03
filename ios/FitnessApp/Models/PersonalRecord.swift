import Foundation
import SwiftData

@Model
final class PersonalRecord {
    @Attribute(.unique) var id: String
    var prType: PRType
    var value: Double?       // For e1RM PRs
    var reps: Int?           // For rep PRs
    var weight: Double?      // For rep PRs
    var achievedAt: Date
    var createdAt: Date

    // Relationships
    var user: User?
    var exercise: Exercise?

    var exerciseName: String {
        exercise?.name ?? "Unknown Exercise"
    }

    var displayValue: String {
        switch prType {
        case .e1rm:
            if let value = value {
                return "\(value.formattedWeight) lb e1RM"
            }
        case .repPR:
            if let reps = reps, let weight = weight {
                return "\(reps) reps @ \(weight.formattedWeight) lb"
            }
        }
        return "PR"
    }

    init(
        id: String = UUID().uuidString,
        prType: PRType,
        value: Double? = nil,
        reps: Int? = nil,
        weight: Double? = nil,
        achievedAt: Date = Date()
    ) {
        self.id = id
        self.prType = prType
        self.value = value
        self.reps = reps
        self.weight = weight
        self.achievedAt = achievedAt
        self.createdAt = Date()
    }
}

enum PRType: String, Codable {
    case e1rm = "e1rm"
    case repPR = "rep_pr"

    var displayName: String {
        switch self {
        case .e1rm: return "e1RM PR"
        case .repPR: return "Rep PR"
        }
    }

    var icon: String {
        switch self {
        case .e1rm: return "trophy.fill"
        case .repPR: return "star.fill"
        }
    }
}
