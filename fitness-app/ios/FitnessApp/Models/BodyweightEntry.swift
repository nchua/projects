import Foundation
import SwiftData

@Model
final class BodyweightEntry {
    @Attribute(.unique) var id: String
    var date: Date
    var weightLb: Double
    var source: String = "manual"
    var createdAt: Date
    var updatedAt: Date

    // Relationships
    var user: User?

    var weightInPreferredUnit: Double {
        guard let unit = user?.preferredUnit else { return weightLb }
        return unit == .kg ? weightLb * 0.453592 : weightLb
    }

    init(
        id: String = UUID().uuidString,
        date: Date = Date(),
        weightLb: Double,
        source: String = "manual"
    ) {
        self.id = id
        self.date = date
        self.weightLb = weightLb
        self.source = source
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
