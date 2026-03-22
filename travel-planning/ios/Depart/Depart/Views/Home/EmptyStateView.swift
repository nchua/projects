import SwiftUI

/// Empty state when no trips exist.
struct EmptyStateView: View {
    let onAddTrip: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "car.circle")
                .font(.system(size: 64))
                .foregroundStyle(Color.departPrimary.opacity(0.4))

            VStack(spacing: 8) {
                Text("No Upcoming Trips")
                    .font(.departTitle3)
                    .foregroundStyle(Color.departTextPrimary)

                Text("Add a trip to start monitoring traffic\nand get smart departure alerts.")
                    .font(.departSubhead)
                    .foregroundStyle(Color.departTextSecondary)
                    .multilineTextAlignment(.center)
            }

            Button(action: onAddTrip) {
                Label("Add First Trip", systemImage: "plus")
                    .font(.departHeadline)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                    .background(Color.departPrimary)
                    .clipShape(Capsule())
            }
        }
        .padding(40)
    }
}
