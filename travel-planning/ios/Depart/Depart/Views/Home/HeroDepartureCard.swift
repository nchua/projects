import SwiftUI

/// Prominent hero card for the next upcoming departure.
struct HeroDepartureCard: View {
    let trip: Trip
    let currentDate: Date // From TimelineView for live updates

    private var minutesRemaining: Int {
        trip.minutesUntilDeparture ?? 0
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Top row: status + last checked
            HStack {
                Text(trip.statusEnum.rawValue.uppercased())
                    .font(.departOverline)
                    .foregroundStyle(.white.opacity(0.7))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(.white.opacity(0.15))
                    .clipShape(Capsule())

                Spacer()

                if let lastChecked = trip.lastCheckedAt {
                    let ago = Int(currentDate.timeIntervalSince(lastChecked) / 60)
                    Text("Updated \(ago) min ago")
                        .font(.departOverline)
                        .foregroundStyle(.white.opacity(0.6))
                }
            }

            // Event name
            Text(trip.name)
                .font(.departTitle2)
                .foregroundStyle(.white)
                .lineLimit(2)

            // Destination
            HStack(spacing: 4) {
                Image(systemName: "mappin")
                    .font(.system(size: 11))
                Text(trip.destAddress)
                    .font(.departCallout)
                    .lineLimit(1)
            }
            .foregroundStyle(.white.opacity(0.8))

            HStack(alignment: .bottom) {
                // Left: departure time + travel info
                VStack(alignment: .leading, spacing: 4) {
                    if let notifyAt = trip.notifyAt {
                        Text(notifyAt.shortTimeString)
                            .font(.departHeroTime)
                            .foregroundStyle(.white)
                    }

                    HStack(spacing: 8) {
                        if let eta = trip.estimatedTravelMinutes {
                            Text("\(eta) min")
                                .font(.departCaption)
                                .foregroundStyle(.white.opacity(0.7))
                        }
                        Text("Buffer: \(trip.bufferMinutes) min")
                            .font(.departCaption)
                            .foregroundStyle(.white.opacity(0.7))
                    }
                }

                Spacer()

                // Right: countdown number
                VStack(spacing: 2) {
                    Text("\(max(0, minutesRemaining))")
                        .font(.departCountdown)
                        .foregroundStyle(.white)
                        .contentTransition(.numericText())

                    Text("min")
                        .font(.departOverline)
                        .foregroundStyle(.white.opacity(0.7))
                }
            }
        }
        .padding(20)
        .background(Color.heroGradient)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: Color.departPrimary.opacity(0.3), radius: 12, x: 0, y: 6)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Next departure: \(trip.name)")
        .accessibilityValue(
            trip.notifyAt != nil
                ? "Leave by \(trip.notifyAt!.shortTimeString). \(minutesRemaining) minutes remaining."
                : "Arriving at \(trip.arrivalTime.shortTimeString)"
        )
    }
}
