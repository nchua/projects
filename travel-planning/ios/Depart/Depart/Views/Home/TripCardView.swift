import SwiftUI

/// Compact trip row for the dashboard list.
struct TripCardView: View {
    let trip: Trip

    var body: some View {
        HStack(spacing: 12) {
            // Status indicator dot
            Circle()
                .fill(trip.urgencyLevel.color)
                .frame(width: 10, height: 10)

            // Trip info
            VStack(alignment: .leading, spacing: 3) {
                Text(trip.name)
                    .font(.departBody)
                    .foregroundStyle(Color.departTextPrimary)
                    .lineLimit(1)

                Text(trip.destAddress)
                    .font(.departCaption)
                    .foregroundStyle(Color.departTextSecondary)
                    .lineLimit(1)
            }

            Spacer()

            // Departure time
            VStack(alignment: .trailing, spacing: 3) {
                if let notifyAt = trip.notifyAt {
                    Text(notifyAt.shortTimeString)
                        .font(.departHeadline)
                        .foregroundStyle(Color.departTextPrimary)
                } else {
                    Text(trip.arrivalTime.shortTimeString)
                        .font(.departHeadline)
                        .foregroundStyle(Color.departTextPrimary)
                }

                if let minutes = trip.estimatedTravelMinutes {
                    Text("\(minutes) min")
                        .font(.departCaption)
                        .foregroundStyle(Color.departTextSecondary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(trip.name), \(trip.destAddress)")
        .accessibilityValue(
            trip.notifyAt != nil
                ? "Depart at \(trip.notifyAt!.shortTimeString)"
                : "Arrives at \(trip.arrivalTime.shortTimeString)"
        )
    }
}
