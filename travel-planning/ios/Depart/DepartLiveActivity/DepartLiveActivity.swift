import ActivityKit
import Foundation

/// Manages Live Activity lifecycle for trip monitoring.
enum LiveActivityManager {
    /// Start a live activity when a trip enters active monitoring.
    static func startActivity(for trip: Trip) {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            print("[LiveActivity] Activities not enabled")
            return
        }

        let attributes = DepartLiveActivityAttributes(
            tripId: trip.id,
            tripName: trip.name,
            destination: trip.destAddress,
            arrivalTime: trip.arrivalTime,
            travelMode: trip.travelMode
        )

        let initialState = DepartLiveActivityAttributes.ContentState(
            minutesRemaining: trip.minutesUntilDeparture ?? 60,
            departureTime: trip.notifyAt ?? trip.arrivalTime,
            etaMinutes: trip.estimatedTravelMinutes ?? 30,
            trafficStatus: "light",
            isOverdue: false
        )

        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: initialState, staleDate: nil),
                pushType: .token
            )
            print("[LiveActivity] Started: \(activity.id) for trip \(trip.name)")
        } catch {
            print("[LiveActivity] Failed to start: \(error)")
        }
    }

    /// Update a running live activity with new ETA/countdown data.
    static func updateActivity(
        tripId: UUID,
        minutesRemaining: Int,
        departureTime: Date,
        etaMinutes: Int,
        trafficStatus: String
    ) {
        let state = DepartLiveActivityAttributes.ContentState(
            minutesRemaining: minutesRemaining,
            departureTime: departureTime,
            etaMinutes: etaMinutes,
            trafficStatus: trafficStatus,
            isOverdue: minutesRemaining < 0
        )

        Task {
            for activity in Activity<DepartLiveActivityAttributes>.activities {
                if activity.attributes.tripId == tripId {
                    await activity.update(.init(state: state, staleDate: nil))
                    return
                }
            }
        }
    }

    /// End a live activity when the user departs or the trip completes.
    static func endActivity(tripId: UUID, departed: Bool = false) {
        let finalState = DepartLiveActivityAttributes.ContentState(
            minutesRemaining: 0,
            departureTime: Date(),
            etaMinutes: 0,
            trafficStatus: departed ? "departed" : "completed",
            isOverdue: false
        )

        Task {
            for activity in Activity<DepartLiveActivityAttributes>.activities {
                if activity.attributes.tripId == tripId {
                    await activity.end(
                        .init(state: finalState, staleDate: nil),
                        dismissalPolicy: .after(Date().addingTimeInterval(300)) // Dismiss after 5 min
                    )
                    return
                }
            }
        }
    }

    /// End all active live activities (e.g., on logout).
    static func endAllActivities() {
        Task {
            for activity in Activity<DepartLiveActivityAttributes>.activities {
                await activity.end(nil, dismissalPolicy: .immediate)
            }
        }
    }
}
