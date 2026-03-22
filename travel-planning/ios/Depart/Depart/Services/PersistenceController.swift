import Foundation
import SwiftData

// MARK: - SwiftData Models

/// Cached trip for offline-first reads.
@Model
final class CachedTrip {
    @Attribute(.unique) var tripId: UUID
    var name: String
    var originAddress: String
    var originLat: Double
    var originLng: Double
    var destAddress: String
    var destLat: Double
    var destLng: Double
    var arrivalTime: Date
    var travelMode: String
    var bufferMinutes: Int
    var status: String
    var lastEtaSeconds: Int?
    var lastCheckedAt: Date?
    var notifyAt: Date?
    var baselineDurationSeconds: Int?
    var notified: Bool
    var notificationCount: Int
    var isRecurring: Bool
    var createdAt: Date
    var updatedAt: Date
    var cachedAt: Date

    init(from trip: Trip) {
        self.tripId = trip.id
        self.name = trip.name
        self.originAddress = trip.originAddress
        self.originLat = trip.originLat
        self.originLng = trip.originLng
        self.destAddress = trip.destAddress
        self.destLat = trip.destLat
        self.destLng = trip.destLng
        self.arrivalTime = trip.arrivalTime
        self.travelMode = trip.travelMode
        self.bufferMinutes = trip.bufferMinutes
        self.status = trip.status
        self.lastEtaSeconds = trip.lastEtaSeconds
        self.lastCheckedAt = trip.lastCheckedAt
        self.notifyAt = trip.notifyAt
        self.baselineDurationSeconds = trip.baselineDurationSeconds
        self.notified = trip.notified
        self.notificationCount = trip.notificationCount
        self.isRecurring = trip.isRecurring
        self.createdAt = trip.createdAt
        self.updatedAt = trip.updatedAt
        self.cachedAt = Date()
    }

    func update(from trip: Trip) {
        name = trip.name
        originAddress = trip.originAddress
        originLat = trip.originLat
        originLng = trip.originLng
        destAddress = trip.destAddress
        destLat = trip.destLat
        destLng = trip.destLng
        arrivalTime = trip.arrivalTime
        travelMode = trip.travelMode
        bufferMinutes = trip.bufferMinutes
        status = trip.status
        lastEtaSeconds = trip.lastEtaSeconds
        lastCheckedAt = trip.lastCheckedAt
        notifyAt = trip.notifyAt
        baselineDurationSeconds = trip.baselineDurationSeconds
        notified = trip.notified
        notificationCount = trip.notificationCount
        isRecurring = trip.isRecurring
        createdAt = trip.createdAt
        updatedAt = trip.updatedAt
        cachedAt = Date()
    }

    func asTrip() -> Trip {
        Trip(
            id: tripId,
            name: name,
            originAddress: originAddress,
            originLat: originLat,
            originLng: originLng,
            originLocationId: nil,
            originIsCurrentLocation: false,
            destAddress: destAddress,
            destLat: destLat,
            destLng: destLng,
            destLocationId: nil,
            arrivalTime: arrivalTime,
            travelMode: travelMode,
            bufferMinutes: bufferMinutes,
            status: status,
            monitoringStartedAt: nil,
            lastEtaSeconds: lastEtaSeconds,
            lastCheckedAt: lastCheckedAt,
            notifyAt: notifyAt,
            baselineDurationSeconds: baselineDurationSeconds,
            notified: notified,
            notificationCount: notificationCount,
            isRecurring: isRecurring,
            recurrenceRule: nil,
            calendarEventId: nil,
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }
}

/// Cached saved location for offline access.
@Model
final class CachedSavedLocation {
    @Attribute(.unique) var locationId: UUID
    var name: String
    var address: String
    var latitude: Double
    var longitude: Double
    var icon: String?
    var sortOrder: Int
    var cachedAt: Date

    init(from location: SavedLocation) {
        self.locationId = location.id
        self.name = location.name
        self.address = location.address
        self.latitude = location.latitude
        self.longitude = location.longitude
        self.icon = location.icon
        self.sortOrder = location.sortOrder
        self.cachedAt = Date()
    }

    func asSavedLocation() -> SavedLocation {
        SavedLocation(
            id: locationId,
            name: name,
            address: address,
            latitude: latitude,
            longitude: longitude,
            icon: icon,
            sortOrder: sortOrder,
            createdAt: cachedAt,
            updatedAt: cachedAt
        )
    }
}

/// Cached user preferences for offline access.
@Model
final class CachedPreferences {
    @Attribute(.unique) var userId: UUID
    var defaultBufferMinutes: Int
    var defaultTravelMode: String
    var quietHoursStart: String?
    var quietHoursEnd: String?
    var timezone: String
    var cachedAt: Date

    init(from profile: UserProfile) {
        self.userId = profile.id
        self.defaultBufferMinutes = profile.defaultBufferMinutes
        self.defaultTravelMode = profile.defaultTravelMode
        self.quietHoursStart = profile.quietHoursStart
        self.quietHoursEnd = profile.quietHoursEnd
        self.timezone = profile.timezone
        self.cachedAt = Date()
    }
}

/// Queued offline write operation.
@Model
final class QueuedWrite {
    var id: UUID
    var endpointPath: String
    var httpMethod: String
    var bodyData: Data?
    var createdAt: Date
    var retryCount: Int

    init(endpointPath: String, httpMethod: String, bodyData: Data?) {
        self.id = UUID()
        self.endpointPath = endpointPath
        self.httpMethod = httpMethod
        self.bodyData = bodyData
        self.createdAt = Date()
        self.retryCount = 0
    }
}

// MARK: - Persistence Controller

/// SwiftData container setup and cache operations.
@Observable
final class PersistenceController {
    static let shared = PersistenceController()

    let container: ModelContainer

    init() {
        let schema = Schema([
            CachedTrip.self,
            CachedSavedLocation.self,
            CachedPreferences.self,
            QueuedWrite.self,
        ])
        let config = ModelConfiguration(isStoredInMemoryOnly: false)
        do {
            container = try ModelContainer(for: schema, configurations: [config])
        } catch {
            fatalError("[PersistenceController] Failed to create ModelContainer: \(error)")
        }
    }

    @MainActor
    var context: ModelContext { container.mainContext }

    // MARK: - Trip Caching

    /// Cache trips from API response.
    @MainActor
    func cacheTrips(_ trips: [Trip]) {
        for trip in trips {
            let predicate = #Predicate<CachedTrip> { $0.tripId == trip.id }
            let descriptor = FetchDescriptor<CachedTrip>(predicate: predicate)
            if let existing = try? context.fetch(descriptor).first {
                existing.update(from: trip)
            } else {
                context.insert(CachedTrip(from: trip))
            }
        }
        try? context.save()
    }

    /// Read cached trips, sorted by arrival time.
    @MainActor
    func fetchCachedTrips() -> [Trip] {
        let now = Date()
        let predicate = #Predicate<CachedTrip> {
            $0.arrivalTime > now && $0.status != "completed" && $0.status != "cancelled"
        }
        var descriptor = FetchDescriptor<CachedTrip>(predicate: predicate)
        descriptor.sortBy = [SortDescriptor(\.arrivalTime)]
        guard let cached = try? context.fetch(descriptor) else { return [] }
        return cached.map { $0.asTrip() }
    }

    /// Remove expired cached trips (completed/cancelled or past arrival + 1 hour).
    @MainActor
    func pruneExpiredTrips() {
        let cutoff = Date().addingTimeInterval(-3600) // 1 hour past arrival
        let predicate = #Predicate<CachedTrip> {
            $0.arrivalTime < cutoff || $0.status == "completed" || $0.status == "cancelled"
        }
        let descriptor = FetchDescriptor<CachedTrip>(predicate: predicate)
        guard let expired = try? context.fetch(descriptor) else { return }
        for trip in expired {
            context.delete(trip)
        }
        try? context.save()
    }

    // MARK: - Saved Location Caching

    @MainActor
    func cacheSavedLocations(_ locations: [SavedLocation]) {
        for location in locations {
            let predicate = #Predicate<CachedSavedLocation> { $0.locationId == location.id }
            let descriptor = FetchDescriptor<CachedSavedLocation>(predicate: predicate)
            if let existing = try? context.fetch(descriptor).first {
                existing.name = location.name
                existing.address = location.address
                existing.latitude = location.latitude
                existing.longitude = location.longitude
                existing.icon = location.icon
                existing.sortOrder = location.sortOrder
                existing.cachedAt = Date()
            } else {
                context.insert(CachedSavedLocation(from: location))
            }
        }
        try? context.save()
    }

    @MainActor
    func fetchCachedSavedLocations() -> [SavedLocation] {
        var descriptor = FetchDescriptor<CachedSavedLocation>()
        descriptor.sortBy = [SortDescriptor(\.sortOrder)]
        guard let cached = try? context.fetch(descriptor) else { return [] }
        return cached.map { $0.asSavedLocation() }
    }

    // MARK: - Offline Write Queue

    /// Queue a failed write for replay when connectivity returns.
    @MainActor
    func enqueueWrite(endpointPath: String, httpMethod: String, body: (any Encodable)?) {
        let bodyData = try? DateCoding.encoder.encode(AnyEncodable(body))
        let queued = QueuedWrite(endpointPath: endpointPath, httpMethod: httpMethod, bodyData: bodyData)
        context.insert(queued)
        try? context.save()
        print("[PersistenceController] Queued offline write: \(httpMethod) \(endpointPath)")
    }

    /// Fetch all queued writes, oldest first.
    @MainActor
    func fetchQueuedWrites() -> [QueuedWrite] {
        var descriptor = FetchDescriptor<QueuedWrite>()
        descriptor.sortBy = [SortDescriptor(\.createdAt)]
        return (try? context.fetch(descriptor)) ?? []
    }

    /// Remove a queued write after successful replay.
    @MainActor
    func dequeueWrite(_ write: QueuedWrite) {
        context.delete(write)
        try? context.save()
    }
}

// MARK: - AnyEncodable Wrapper

/// Type-erased Encodable for serializing queued write bodies.
private struct AnyEncodable: Encodable {
    private let _encode: (Encoder) throws -> Void

    init(_ value: (any Encodable)?) {
        if let value {
            _encode = { encoder in
                try value.encode(to: encoder)
            }
        } else {
            _encode = { encoder in
                var container = encoder.singleValueContainer()
                try container.encodeNil()
            }
        }
    }

    func encode(to encoder: Encoder) throws {
        try _encode(encoder)
    }
}
