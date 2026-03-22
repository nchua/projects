import ActivityKit
import SwiftUI
import WidgetKit

/// Lock screen expanded view and Dynamic Island layouts.
struct DepartLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: DepartLiveActivityAttributes.self) { context in
            // Lock screen / notification banner view
            lockScreenView(context: context)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded Dynamic Island regions
                DynamicIslandExpandedRegion(.leading) {
                    Label(context.attributes.tripName, systemImage: travelModeIcon(context.attributes.travelMode))
                        .font(.caption)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(context.state.minutesRemaining) min")
                        .font(.title3.bold())
                        .foregroundStyle(urgencyColor(context.state))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    HStack {
                        Text(context.attributes.destination)
                            .font(.caption2)
                            .lineLimit(1)
                        Spacer()
                        Text("Leave by \(context.state.departureTime.formatted(date: .omitted, time: .shortened))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            } compactLeading: {
                // Compact left: app icon + trip name
                Image(systemName: travelModeIcon(context.attributes.travelMode))
                    .font(.caption2)
            } compactTrailing: {
                // Compact right: countdown
                Text("\(context.state.minutesRemaining)m")
                    .font(.caption2.bold())
                    .foregroundStyle(urgencyColor(context.state))
            } minimal: {
                // Minimal: just the countdown
                Text("\(context.state.minutesRemaining)")
                    .font(.caption2.bold())
                    .foregroundStyle(urgencyColor(context.state))
            }
        }
    }

    // MARK: - Lock Screen View

    @ViewBuilder
    private func lockScreenView(context: ActivityViewContext<DepartLiveActivityAttributes>) -> some View {
        VStack(spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(context.attributes.tripName)
                        .font(.headline)
                    Text(context.attributes.destination)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                // Countdown
                VStack(spacing: 0) {
                    Text("\(context.state.minutesRemaining)")
                        .font(.system(size: 32, weight: .heavy, design: .rounded))
                        .foregroundStyle(urgencyColor(context.state))
                        .contentTransition(.numericText())
                    Text("min")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // Progress bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(.quaternary)
                        .frame(height: 4)

                    Capsule()
                        .fill(urgencyColor(context.state))
                        .frame(
                            width: geometry.size.width * progressFraction(context.state),
                            height: 4
                        )
                }
            }
            .frame(height: 4)

            HStack {
                Label(
                    "Leave by \(context.state.departureTime.formatted(date: .omitted, time: .shortened))",
                    systemImage: "clock"
                )
                .font(.caption)

                Spacer()

                Label(
                    "\(context.state.etaMinutes) min \(context.state.trafficStatus)",
                    systemImage: "car.fill"
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding()
        .activityBackgroundTint(.black.opacity(0.8))
    }

    // MARK: - Helpers

    private func travelModeIcon(_ mode: String) -> String {
        switch mode {
        case "transit": return "bus.fill"
        case "walking": return "figure.walk"
        case "cycling": return "bicycle"
        default: return "car.fill"
        }
    }

    private func urgencyColor(_ state: DepartLiveActivityAttributes.ContentState) -> Color {
        if state.isOverdue || state.minutesRemaining < 0 { return .red }
        if state.minutesRemaining < 10 { return .red }
        if state.minutesRemaining < 30 { return .orange }
        return .green
    }

    private func progressFraction(_ state: DepartLiveActivityAttributes.ContentState) -> Double {
        guard state.etaMinutes > 0 else { return 0 }
        let total = Double(state.etaMinutes + 30) // rough total
        let elapsed = total - Double(state.minutesRemaining)
        return min(max(elapsed / total, 0), 1)
    }
}
