import Foundation

// MARK: - API Error

enum APIError: Error, LocalizedError {
    case unauthorized
    case networkError(Error)
    case serverError(Int, String)
    case decodingError(Error)
    case offline
    case invalidURL
    case unknown

    var errorDescription: String? {
        switch self {
        case .unauthorized: return "Session expired. Please restart the app."
        case .networkError(let error): return "Network error: \(error.localizedDescription)"
        case .serverError(_, let message): return message
        case .decodingError(let error): return "Data error: \(error.localizedDescription)"
        case .offline: return "No internet connection."
        case .invalidURL: return "Invalid request URL."
        case .unknown: return "An unexpected error occurred."
        }
    }
}

// MARK: - HTTP Method

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

// MARK: - Endpoint

enum Endpoint {
    // Auth
    case register
    case login
    case appleAuth
    case refreshToken

    // User
    case userProfile
    case updateProfile

    // Trips
    case trips
    case upcomingTrips
    case tripDetail(UUID)
    case createTrip
    case updateTrip(UUID)
    case deleteTrip(UUID)

    // Saved Locations
    case savedLocations
    case savedLocation(UUID)
    case updateSavedLocation(UUID)
    case deleteSavedLocation(UUID)

    // Device Tokens
    case registerDeviceToken
    case unregisterDeviceToken

    var path: String {
        switch self {
        case .register: return "/auth/register"
        case .login: return "/auth/login"
        case .appleAuth: return "/auth/apple"
        case .refreshToken: return "/auth/refresh"
        case .userProfile, .updateProfile: return "/users/me"
        case .trips, .createTrip: return "/trips"
        case .upcomingTrips: return "/trips/upcoming"
        case .tripDetail(let id), .updateTrip(let id): return "/trips/\(id)"
        case .deleteTrip(let id): return "/trips/\(id)"
        case .savedLocations: return "/locations"
        case .savedLocation(let id), .updateSavedLocation(let id), .deleteSavedLocation(let id):
            return "/locations/\(id)"
        case .registerDeviceToken, .unregisterDeviceToken: return "/device-tokens"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .register, .login, .appleAuth, .refreshToken,
             .createTrip, .registerDeviceToken:
            return .post
        case .userProfile, .trips, .upcomingTrips, .tripDetail,
             .savedLocations, .savedLocation:
            return .get
        case .updateTrip, .updateSavedLocation: return .put
        case .updateProfile: return .patch
        case .deleteTrip, .deleteSavedLocation, .unregisterDeviceToken: return .delete
        }
    }

    /// Whether this endpoint requires auth headers.
    var requiresAuth: Bool {
        switch self {
        case .register, .login, .appleAuth, .refreshToken:
            return false
        default:
            return true
        }
    }
}

// MARK: - Date Coding

/// Custom ISO 8601 date formatter that handles fractional seconds.
/// Backend may return dates like "2026-03-22T10:30:00.123456+00:00".
enum DateCoding {
    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)

            // Try ISO8601 with fractional seconds first
            let formatterWithFrac = ISO8601DateFormatter()
            formatterWithFrac.formatOptions = [
                .withInternetDateTime,
                .withFractionalSeconds,
            ]
            if let date = formatterWithFrac.date(from: string) {
                return date
            }

            // Fall back to standard ISO8601
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: string) {
                return date
            }

            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath,
                      debugDescription: "Cannot decode date: \(string)")
            )
        }
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            try container.encode(formatter.string(from: date))
        }
        return encoder
    }()
}

// MARK: - API Client

/// Networking layer for all backend communication.
/// Uses URLSession with async/await. Handles auth token injection and refresh.
@Observable
final class APIClient {
    static let shared = APIClient()

    private let baseURL: URL
    private let session: URLSession
    private var authManager: AuthManager?

    init(
        baseURL: URL = URL(string: "https://backend-production-e316.up.railway.app/api/v1")!
    ) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    /// Set the auth manager (called during app setup to break circular init).
    func configure(authManager: AuthManager) {
        self.authManager = authManager
    }

    // MARK: - Generic Request

    /// Make an authenticated API request and decode the response.
    func request<T: Decodable>(
        _ endpoint: Endpoint,
        body: (any Encodable)? = nil,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        let data = try await rawRequest(endpoint, body: body, queryItems: queryItems)
        do {
            return try DateCoding.decoder.decode(T.self, from: data)
        } catch {
            print("[APIClient] Decode error for \(endpoint.path): \(error)")
            if let json = String(data: data, encoding: .utf8) {
                print("[APIClient] Raw response: \(json.prefix(500))")
            }
            throw APIError.decodingError(error)
        }
    }

    /// Make an API request that returns no body (e.g., DELETE -> 204).
    func requestNoContent(
        _ endpoint: Endpoint,
        body: (any Encodable)? = nil
    ) async throws {
        _ = try await rawRequest(endpoint, body: body)
    }

    // MARK: - Raw Request

    private func rawRequest(
        _ endpoint: Endpoint,
        body: (any Encodable)? = nil,
        queryItems: [URLQueryItem]? = nil,
        isRetry: Bool = false
    ) async throws -> Data {
        // Build URL
        var components = URLComponents(url: baseURL.appendingPathComponent(endpoint.path), resolvingAgainstBaseURL: false)
        if let queryItems, !queryItems.isEmpty {
            components?.queryItems = queryItems
        }

        guard let url = components?.url else {
            throw APIError.invalidURL
        }

        // Build request
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Auth header
        if endpoint.requiresAuth {
            if let token = authManager?.getAccessToken() {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
        }

        // Body
        if let body {
            request.httpBody = try DateCoding.encoder.encode(body)
        }

        // Execute
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch let urlError as URLError {
            if urlError.code == .notConnectedToInternet || urlError.code == .networkConnectionLost {
                throw APIError.offline
            }
            throw APIError.networkError(urlError)
        } catch {
            throw APIError.networkError(error)
        }

        // Handle response
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.unknown
        }

        switch httpResponse.statusCode {
        case 200...299:
            return data

        case 401:
            // Attempt token refresh once
            if !isRetry, let authManager {
                do {
                    try await authManager.refreshTokenIfNeeded(force: true)
                    return try await rawRequest(endpoint, body: body, queryItems: queryItems, isRetry: true)
                } catch {
                    authManager.logout()
                    throw APIError.unauthorized
                }
            }
            throw APIError.unauthorized

        case 500...599:
            // Retry transient server errors once
            if !isRetry {
                try await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
                return try await rawRequest(endpoint, body: body, queryItems: queryItems, isRetry: true)
            }
            let message = parseErrorMessage(from: data)
            throw APIError.serverError(httpResponse.statusCode, message)

        default:
            let message = parseErrorMessage(from: data)
            throw APIError.serverError(httpResponse.statusCode, message)
        }
    }

    private func parseErrorMessage(from data: Data) -> String {
        if let errorResponse = try? DateCoding.decoder.decode(APIErrorResponse.self, from: data) {
            return errorResponse.detail
        }
        return "Unknown error"
    }

    // MARK: - Typed Convenience Methods

    // Auth
    func register(email: String, password: String, displayName: String?, timezone: String = "America/Los_Angeles") async throws -> AuthResponse {
        let body = RegisterRequest(email: email, password: password, displayName: displayName, timezone: timezone)
        return try await request(.register, body: body)
    }

    func login(email: String, password: String) async throws -> AuthResponse {
        let body = LoginRequest(email: email, password: password)
        return try await request(.login, body: body)
    }

    func refreshToken(_ token: String) async throws -> AuthResponse {
        let body = RefreshTokenRequest(refreshToken: token)
        return try await request(.refreshToken, body: body)
    }

    // User
    func fetchProfile() async throws -> UserProfile {
        try await request(.userProfile)
    }

    func updateProfile(_ update: UpdateUserRequest) async throws -> UserProfile {
        try await request(.updateProfile, body: update)
    }

    // Trips
    func fetchUpcomingTrips() async throws -> [Trip] {
        try await request(.upcomingTrips)
    }

    func fetchTrips(
        status: String? = nil,
        fromDate: Date? = nil,
        toDate: Date? = nil,
        sortBy: String = "arrival_time",
        sortOrder: String = "asc",
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> PaginatedTripResponse {
        var queryItems: [URLQueryItem] = [
            .init(name: "sort_by", value: sortBy),
            .init(name: "sort_order", value: sortOrder),
            .init(name: "limit", value: "\(limit)"),
            .init(name: "offset", value: "\(offset)"),
        ]
        if let status { queryItems.append(.init(name: "status", value: status)) }
        if let fromDate {
            let formatter = ISO8601DateFormatter()
            queryItems.append(.init(name: "from_date", value: formatter.string(from: fromDate)))
        }
        if let toDate {
            let formatter = ISO8601DateFormatter()
            queryItems.append(.init(name: "to_date", value: formatter.string(from: toDate)))
        }
        return try await request(.trips, queryItems: queryItems)
    }

    func fetchTripDetail(tripId: UUID) async throws -> TripDetailResponse {
        try await request(.tripDetail(tripId))
    }

    func createTrip(_ trip: CreateTripRequest) async throws -> Trip {
        try await request(.createTrip, body: trip)
    }

    func updateTrip(tripId: UUID, _ update: UpdateTripRequest) async throws -> Trip {
        try await request(.updateTrip(tripId), body: update)
    }

    func deleteTrip(tripId: UUID) async throws {
        try await requestNoContent(.deleteTrip(tripId))
    }

    func markDeparted(tripId: UUID) async throws -> Trip {
        let update = UpdateTripRequest(status: "departed")
        return try await updateTrip(tripId: tripId, update)
    }

    func snoozeTrip(tripId: UUID, minutes: Int, currentArrivalTime: Date) async throws -> Trip {
        let newArrival = currentArrivalTime.addingTimeInterval(TimeInterval(minutes * 60))
        let update = UpdateTripRequest(arrivalTime: newArrival)
        return try await updateTrip(tripId: tripId, update)
    }

    // Saved Locations
    func fetchSavedLocations() async throws -> [SavedLocation] {
        try await request(.savedLocations)
    }

    func createSavedLocation(_ location: CreateSavedLocationRequest) async throws -> SavedLocation {
        try await request(.savedLocations, body: location)
    }

    func updateSavedLocation(locationId: UUID, _ update: UpdateSavedLocationRequest) async throws -> SavedLocation {
        try await request(.updateSavedLocation(locationId), body: update)
    }

    func deleteSavedLocation(locationId: UUID) async throws {
        try await requestNoContent(.deleteSavedLocation(locationId))
    }

    // Device Tokens
    func registerDeviceToken(_ token: String) async throws {
        let body = RegisterDeviceTokenRequest(token: token, platform: "ios")
        let _: DeviceTokenResponse = try await request(.registerDeviceToken, body: body)
    }

    func unregisterDeviceToken(_ token: String) async throws {
        let body = UnregisterDeviceTokenRequest(token: token)
        try await requestNoContent(.unregisterDeviceToken, body: body)
    }
}
