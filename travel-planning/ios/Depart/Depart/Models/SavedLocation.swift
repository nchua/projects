import Foundation

/// Matches backend `app/schemas/saved_location.py` SavedLocationResponse exactly.
struct SavedLocation: Identifiable, Codable, Hashable {
    let id: UUID
    var name: String
    var address: String
    var latitude: Double
    var longitude: Double
    var icon: String?
    var sortOrder: Int
    var createdAt: Date
    var updatedAt: Date
}
