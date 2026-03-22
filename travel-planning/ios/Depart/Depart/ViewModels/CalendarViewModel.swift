import EventKit
import Foundation

/// Model for calendar events displayed in the Calendar tab.
struct CalendarEvent: Identifiable {
    let id: String
    let title: String
    let location: String
    let startDate: Date
    let endDate: Date
    var isMonitored: Bool
    let eventIdentifier: String
}

/// ViewModel for the Calendar tab.
@Observable
final class CalendarViewModel {
    var events: [CalendarEvent] = []
    var isCalendarAuthorized = false
    var isLoading = false
    var error: String?

    private var apiClient: APIClient?
    private let calendarService = CalendarService.shared

    func configure(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Calendar Access

    func requestCalendarAccess() async {
        let granted = await calendarService.requestAccess()
        isCalendarAuthorized = granted
        if granted {
            await loadEvents()
        }
    }

    // MARK: - Load Events

    func loadEvents() async {
        isCalendarAuthorized = calendarService.isAuthorized
        guard isCalendarAuthorized else { return }

        isLoading = true
        let ekEvents = calendarService.fetchEventsWithLocations()
        events = ekEvents.map { event in
            CalendarEvent(
                id: event.eventIdentifier,
                title: event.title ?? "Event",
                location: event.location ?? "",
                startDate: event.startDate,
                endDate: event.endDate,
                isMonitored: false, // TODO: check against existing trips
                eventIdentifier: event.eventIdentifier
            )
        }
        isLoading = false
    }

    // MARK: - Sync

    func syncCalendar(apiClient: APIClient) async {
        isLoading = true
        let ekEvents = calendarService.fetchEventsWithLocations()
        _ = await calendarService.createTripsFromEvents(
            ekEvents,
            apiClient: apiClient,
            defaultOrigin: nil
        )
        await loadEvents()
        isLoading = false
    }

    // MARK: - Toggle Monitoring

    func toggleMonitoring(event: CalendarEvent, enabled: Bool) async {
        guard let index = events.firstIndex(where: { $0.id == event.id }) else { return }
        events[index].isMonitored = enabled

        if enabled {
            // Create trip from calendar event
            // TODO: Implement single event trip creation
        } else {
            // Cancel monitoring for this event's trip
            // TODO: Find and delete trip by calendarEventId
        }
    }
}
