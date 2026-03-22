import SwiftUI
import WidgetKit

// MARK: - Timeline Entry

struct DepartWidgetEntry: TimelineEntry {
    let date: Date
    let tripName: String?
    let destination: String?
    let minutesUntilDeparture: Int?
    let departureTime: Date?
    let trafficStatus: String?
    let isEmpty: Bool
}

// MARK: - Timeline Provider

struct DepartWidgetTimeline: TimelineProvider {
    func placeholder(in context: Context) -> DepartWidgetEntry {
        DepartWidgetEntry(
            date: Date(),
            tripName: "Work Commute",
            destination: "123 Main St",
            minutesUntilDeparture: 42,
            departureTime: Date().addingTimeInterval(42 * 60),
            trafficStatus: "light",
            isEmpty: false
        )
    }

    func getSnapshot(in context: Context, completion: @escaping (DepartWidgetEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<DepartWidgetEntry>) -> Void) {
        // Read cached trip data from shared UserDefaults (app group)
        let entry = loadNextTripEntry()
        // Refresh every 15 minutes
        let nextUpdate = Date().addingTimeInterval(15 * 60)
        let timeline = Timeline(entries: [entry], policy: .after(nextUpdate))
        completion(timeline)
    }

    private func loadNextTripEntry() -> DepartWidgetEntry {
        let defaults = UserDefaults(suiteName: "group.com.depart.app")

        guard let tripName = defaults?.string(forKey: "widget.nextTrip.name"),
              let destination = defaults?.string(forKey: "widget.nextTrip.destination")
        else {
            return DepartWidgetEntry(
                date: Date(),
                tripName: nil,
                destination: nil,
                minutesUntilDeparture: nil,
                departureTime: nil,
                trafficStatus: nil,
                isEmpty: true
            )
        }

        let departureInterval = defaults?.double(forKey: "widget.nextTrip.departureTime") ?? 0
        let departureTime = departureInterval > 0 ? Date(timeIntervalSince1970: departureInterval) : nil
        let minutes = departureTime.map { Int($0.timeIntervalSinceNow / 60) }
        let traffic = defaults?.string(forKey: "widget.nextTrip.trafficStatus")

        return DepartWidgetEntry(
            date: Date(),
            tripName: tripName,
            destination: destination,
            minutesUntilDeparture: minutes,
            departureTime: departureTime,
            trafficStatus: traffic,
            isEmpty: false
        )
    }
}

// MARK: - Widget Entry View

struct DepartWidgetEntryView: View {
    var entry: DepartWidgetEntry
    @Environment(\.widgetFamily) var family

    var body: some View {
        if entry.isEmpty {
            emptyView
        } else {
            tripView
        }
    }

    // MARK: - Trip View

    private var tripView: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Trip name
            Text(entry.tripName ?? "Trip")
                .font(.caption.bold())
                .lineLimit(1)

            // Destination
            HStack(spacing: 2) {
                Image(systemName: "mappin")
                    .font(.system(size: 8))
                Text(entry.destination ?? "")
                    .font(.caption2)
                    .lineLimit(1)
            }
            .foregroundStyle(.secondary)

            Spacer()

            // Countdown
            HStack(alignment: .bottom) {
                if let minutes = entry.minutesUntilDeparture {
                    Text("\(max(0, minutes))")
                        .font(.system(size: 28, weight: .heavy, design: .rounded))
                        .foregroundStyle(countdownColor)
                        .contentTransition(.numericText())

                    Text("min")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.bottom, 4)
                }

                Spacer()

                // Traffic dot
                if let traffic = entry.trafficStatus {
                    Circle()
                        .fill(trafficColor(traffic))
                        .frame(width: 8, height: 8)
                }
            }
        }
        .padding()
    }

    // MARK: - Empty View

    private var emptyView: some View {
        VStack(spacing: 8) {
            Image(systemName: "car.fill")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No upcoming trips")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text("Tap to add one")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    private var countdownColor: Color {
        guard let minutes = entry.minutesUntilDeparture else { return .primary }
        if minutes < 0 { return .red }
        if minutes < 10 { return .red }
        if minutes < 30 { return .orange }
        return .green
    }

    private func trafficColor(_ status: String) -> Color {
        switch status {
        case "light": return .green
        case "moderate": return .yellow
        case "heavy": return .orange
        case "severe": return .red
        default: return .gray
        }
    }
}

// MARK: - Widget Configuration

struct DepartWidget: Widget {
    let kind: String = "DepartWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: DepartWidgetTimeline()) { entry in
            DepartWidgetEntryView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Next Departure")
        .description("See your next trip countdown at a glance.")
        .supportedFamilies([.systemSmall])
    }
}

// MARK: - Widget Bundle

@main
struct DepartWidgetBundle: WidgetBundle {
    var body: some Widget {
        DepartWidget()
    }
}
