import Foundation
import SwiftData

@Model
final class Exercise {
    @Attribute(.unique) var id: String
    var name: String
    var canonicalId: String?
    var category: ExerciseCategory
    var primaryMuscle: String?
    var secondaryMuscles: [String] = []
    var isCustom: Bool = false
    var isFavorite: Bool = false
    var createdAt: Date

    // Relationships
    @Relationship(deleteRule: .cascade, inverse: \WorkoutExercise.exercise)
    var workoutExercises: [WorkoutExercise] = []

    @Relationship(deleteRule: .cascade, inverse: \PersonalRecord.exercise)
    var personalRecords: [PersonalRecord] = []

    init(
        id: String = UUID().uuidString,
        name: String,
        category: ExerciseCategory,
        primaryMuscle: String? = nil,
        isCustom: Bool = false
    ) {
        self.id = id
        self.name = name
        self.category = category
        self.primaryMuscle = primaryMuscle
        self.isCustom = isCustom
        self.createdAt = Date()
    }
}

enum ExerciseCategory: String, Codable, CaseIterable {
    case push = "Push"
    case pull = "Pull"
    case legs = "Legs"
    case core = "Core"
    case accessories = "Accessories"

    var icon: String {
        switch self {
        case .push: return "arrow.up.circle"
        case .pull: return "arrow.down.circle"
        case .legs: return "figure.walk"
        case .core: return "circle.grid.cross"
        case .accessories: return "dumbbell"
        }
    }

    var color: String {
        switch self {
        case .push: return "FF6B35"
        case .pull: return "4ECDC4"
        case .legs: return "9B59B6"
        case .core: return "F39C12"
        case .accessories: return "3498DB"
        }
    }
}
