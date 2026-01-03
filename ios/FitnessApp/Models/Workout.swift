import Foundation
import SwiftData

@Model
final class WorkoutSession {
    @Attribute(.unique) var id: String
    var date: Date
    var durationMinutes: Int?
    var sessionRPE: Int?
    var notes: String?
    var syncedAt: Date?
    var deletedAt: Date?
    var createdAt: Date
    var updatedAt: Date

    // Relationships
    var user: User?

    @Relationship(deleteRule: .cascade, inverse: \WorkoutExercise.session)
    var workoutExercises: [WorkoutExercise] = []

    var isDeleted: Bool {
        deletedAt != nil
    }

    var exerciseCount: Int {
        workoutExercises.count
    }

    var totalSets: Int {
        workoutExercises.reduce(0) { $0 + $1.sets.count }
    }

    var totalVolume: Double {
        workoutExercises.reduce(0) { total, we in
            total + we.sets.reduce(0) { $0 + $1.weight * Double($1.reps) }
        }
    }

    init(
        id: String = UUID().uuidString,
        date: Date = Date(),
        notes: String? = nil
    ) {
        self.id = id
        self.date = date
        self.notes = notes
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}

@Model
final class WorkoutExercise {
    @Attribute(.unique) var id: String
    var orderIndex: Int
    var createdAt: Date

    // Relationships
    var session: WorkoutSession?
    var exercise: Exercise?

    @Relationship(deleteRule: .cascade, inverse: \ExerciseSet.workoutExercise)
    var sets: [ExerciseSet] = []

    var exerciseName: String {
        exercise?.name ?? "Unknown Exercise"
    }

    var bestE1RM: Double? {
        sets.compactMap { $0.e1rm }.max()
    }

    init(
        id: String = UUID().uuidString,
        orderIndex: Int = 0
    ) {
        self.id = id
        self.orderIndex = orderIndex
        self.createdAt = Date()
    }
}

@Model
final class ExerciseSet {
    @Attribute(.unique) var id: String
    var weight: Double
    var weightUnit: WeightUnit = WeightUnit.lb
    var reps: Int
    var rpe: Int?
    var rir: Int?
    var setNumber: Int
    var e1rm: Double?
    var createdAt: Date

    // Relationships
    var workoutExercise: WorkoutExercise?

    init(
        id: String = UUID().uuidString,
        weight: Double,
        reps: Int,
        setNumber: Int,
        rpe: Int? = nil,
        rir: Int? = nil
    ) {
        self.id = id
        self.weight = weight
        self.reps = reps
        self.setNumber = setNumber
        self.rpe = rpe
        self.rir = rir
        self.createdAt = Date()
    }

    func calculateE1RM(formula: E1RMFormula = .epley) -> Double {
        var adjustedReps = reps

        if let rpe = rpe {
            adjustedReps += (10 - rpe)
        } else if let rir = rir {
            adjustedReps += rir
        }

        let calculated = formula.calculate(weight: weight, reps: adjustedReps)
        self.e1rm = calculated
        return calculated
    }
}
