import Foundation
import SwiftData

@Model
final class User {
    @Attribute(.unique) var id: String
    var email: String
    var createdAt: Date

    // Relationships
    @Relationship(deleteRule: .cascade, inverse: \WorkoutSession.user)
    var workoutSessions: [WorkoutSession] = []

    @Relationship(deleteRule: .cascade, inverse: \BodyweightEntry.user)
    var bodyweightEntries: [BodyweightEntry] = []

    @Relationship(deleteRule: .cascade, inverse: \PersonalRecord.user)
    var personalRecords: [PersonalRecord] = []

    // Profile data (embedded)
    var age: Int?
    var sex: Sex?
    var bodyweightLb: Double?
    var heightInches: Double?
    var trainingExperience: TrainingExperience?
    var preferredUnit: WeightUnit = WeightUnit.lb
    var e1rmFormula: E1RMFormula = E1RMFormula.epley

    init(id: String = UUID().uuidString, email: String) {
        self.id = id
        self.email = email
        self.createdAt = Date()
    }
}

enum Sex: String, Codable, CaseIterable {
    case male
    case female
}

enum TrainingExperience: String, Codable, CaseIterable {
    case beginner = "beginner"
    case novice = "novice"
    case intermediate = "intermediate"
    case advanced = "advanced"
    case elite = "elite"

    var displayName: String {
        rawValue.capitalized
    }
}

enum WeightUnit: String, Codable, CaseIterable {
    case lb
    case kg

    var displayName: String {
        rawValue.uppercased()
    }

    func convert(_ value: Double, to target: WeightUnit) -> Double {
        if self == target { return value }
        switch (self, target) {
        case (.lb, .kg): return value * 0.453592
        case (.kg, .lb): return value * 2.20462
        default: return value
        }
    }
}

enum E1RMFormula: String, Codable, CaseIterable {
    case epley
    case brzycki
    case wathan
    case lombardi

    var displayName: String {
        rawValue.capitalized
    }

    func calculate(weight: Double, reps: Int) -> Double {
        guard reps > 0 else { return weight }
        if reps == 1 { return weight }

        switch self {
        case .epley:
            return weight * (1 + Double(reps) / 30)
        case .brzycki:
            return weight * (36 / (37 - Double(reps)))
        case .wathan:
            return (100 * weight) / (48.8 + 53.8 * exp(-0.075 * Double(reps)))
        case .lombardi:
            return weight * pow(Double(reps), 0.1)
        }
    }
}
