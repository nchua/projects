import MapKit
import SwiftUI

/// Full trip detail: map hero, countdown, details, alert history, actions.
struct TripDetailView: View {
    let tripId: UUID
    @Environment(APIClient.self) private var apiClient
    @Environment(\.dismiss) private var dismiss

    @State private var viewModel = TripDetailViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Map hero
                if let trip = viewModel.trip {
                    TripMapView(
                        originCoordinate: CLLocationCoordinate2D(
                            latitude: trip.originLat,
                            longitude: trip.originLng
                        ),
                        destCoordinate: CLLocationCoordinate2D(
                            latitude: trip.destLat,
                            longitude: trip.destLng
                        ),
                        route: $viewModel.route
                    )
                    .frame(height: 250)
                    .clipShape(
                        UnevenRoundedRectangle(
                            topLeadingRadius: 0, bottomLeadingRadius: 20,
                            bottomTrailingRadius: 20, topTrailingRadius: 0
                        )
                    )
                }

                VStack(spacing: 16) {
                    // Status banner
                    if let trip = viewModel.trip {
                        StatusBannerView(status: trip.statusEnum)
                    }

                    // Countdown ring
                    TimelineView(.periodic(from: .now, by: 1.0)) { context in
                        if let trip = viewModel.trip,
                           let minutesRemaining = trip.minutesUntilDeparture {
                            let totalMinutes = (trip.lastEtaSeconds ?? 3600) / 60 + trip.bufferMinutes
                            CountdownRingView(
                                minutesRemaining: minutesRemaining,
                                totalMinutes: totalMinutes,
                                leaveByTime: trip.notifyAt
                            )
                            .padding(.vertical, 8)
                        }
                    }

                    // Trip details card
                    if let trip = viewModel.trip {
                        tripDetailsCard(trip)
                    }

                    // Alert history
                    AlertHistoryCard(notifications: viewModel.notifications)

                    // Action buttons
                    if let trip = viewModel.trip {
                        actionButtons(trip)
                    }
                }
                .padding(16)
            }
        }
        .navigationTitle(viewModel.trip?.name ?? "Trip Detail")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            viewModel.configure(apiClient: apiClient)
            await viewModel.loadDetail(tripId: tripId)
        }
    }

    // MARK: - Trip Details Card

    private func tripDetailsCard(_ trip: Trip) -> some View {
        VStack(spacing: 12) {
            detailRow(icon: "mappin.circle.fill", label: "Destination", value: trip.destAddress)
            Divider()
            detailRow(icon: "location.circle.fill", label: "Origin", value: trip.originAddress)
            Divider()
            detailRow(icon: "clock.fill", label: "Arrive by", value: trip.arrivalTime.shortTimeString)
            Divider()

            if let eta = trip.estimatedTravelMinutes {
                detailRow(icon: "car.fill", label: "Travel time", value: "\(eta) min")
                Divider()
            }

            detailRow(icon: "plus.circle.fill", label: "Buffer", value: "\(trip.bufferMinutes) min")

            if let lastChecked = trip.lastCheckedAt {
                Divider()
                detailRow(
                    icon: "antenna.radiowaves.left.and.right",
                    label: "Last checked",
                    value: lastChecked.shortTimeString
                )
            }
        }
        .departCard()
    }

    private func detailRow(icon: String, label: String, value: String) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(Color.departPrimary)
                .frame(width: 24)
            Text(label)
                .font(.departCaption)
                .foregroundStyle(Color.departTextSecondary)
            Spacer()
            Text(value)
                .font(.departBody)
                .foregroundStyle(Color.departTextPrimary)
                .lineLimit(1)
        }
    }

    // MARK: - Action Buttons

    private func actionButtons(_ trip: Trip) -> some View {
        VStack(spacing: 10) {
            // Open in Maps
            Button {
                viewModel.openInMaps()
            } label: {
                Label("Open in Maps", systemImage: "map.fill")
                    .font(.departHeadline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.departPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            HStack(spacing: 10) {
                // Snooze
                Button {
                    Task { await viewModel.snoozeTenMinutes() }
                } label: {
                    Label("Snooze 10 min", systemImage: "clock.arrow.circlepath")
                        .font(.departCaption)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.departSurface)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                // I've Left
                Button {
                    Task {
                        await viewModel.markDeparted()
                        dismiss()
                    }
                } label: {
                    Label("I've Left", systemImage: "figure.walk")
                        .font(.departCaption)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Color.departSurface)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
    }
}
