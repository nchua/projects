import SwiftUI

/// Main home dashboard with hero card, trip sections, and FAB.
struct HomeView: View {
    @Environment(APIClient.self) private var apiClient
    @Environment(AppState.self) private var appState
    @Environment(NavigationRouter.self) private var router

    @State private var viewModel = HomeViewModel()
    @State private var showAddTrip = false
    @State private var savedLocations: [SavedLocation] = []

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Offline banner
                if appState.isOffline {
                    OfflineBannerView()
                        .padding(.horizontal)
                }

                // Content based on state
                if viewModel.isLoading && viewModel.nextDeparture == nil {
                    ProgressView()
                        .padding(.top, 60)
                } else if viewModel.nextDeparture == nil && viewModel.laterToday.isEmpty && viewModel.tomorrow.isEmpty {
                    EmptyStateView { showAddTrip = true }
                        .padding(.top, 40)
                } else {
                    tripContent
                }
            }
            .padding(.top, 8)
        }
        .refreshable {
            await viewModel.loadTrips()
        }
        .navigationTitle("Depart")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showAddTrip = true
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                        .foregroundStyle(Color.departPrimary)
                }
                .accessibilityLabel("Add new trip")
            }
        }
        .sheet(isPresented: $showAddTrip) {
            AddTripView(savedLocations: savedLocations) {
                Task { await viewModel.loadTrips() }
            }
        }
        .task {
            viewModel.configure(apiClient: apiClient)
            await viewModel.loadTrips()
            await loadSavedLocations()
        }
        .onReceive(NotificationCenter.default.publisher(for: .showAddTrip)) { _ in
            showAddTrip = true
        }
    }

    // MARK: - Trip Content

    @ViewBuilder
    private var tripContent: some View {
        // Use TimelineView for live countdown updates
        TimelineView(.periodic(from: .now, by: 1.0)) { context in
            VStack(spacing: 16) {
                // Hero card for next departure
                if let next = viewModel.nextDeparture {
                    NavigationLink(value: DeepLinkDestination.tripDetail(next.id)) {
                        HeroDepartureCard(trip: next, currentDate: context.date)
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal)
                }

                // Later Today section
                if !viewModel.laterToday.isEmpty {
                    tripSection(title: "Later Today", trips: viewModel.laterToday)
                }

                // Tomorrow section
                if !viewModel.tomorrow.isEmpty {
                    tripSection(title: "Tomorrow", trips: viewModel.tomorrow)
                }
            }
        }
    }

    private func tripSection(title: String, trips: [Trip]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeaderView(title: title, trailing: "\(trips.count) trips")
                .padding(.horizontal)

            VStack(spacing: 0) {
                ForEach(trips) { trip in
                    NavigationLink(value: DeepLinkDestination.tripDetail(trip.id)) {
                        TripCardView(trip: trip)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                    }
                    .buttonStyle(.plain)
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) {
                            Task { await viewModel.deleteTrip(trip) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }

                    if trip.id != trips.last?.id {
                        Divider()
                            .padding(.leading, 36)
                    }
                }
            }
            .departCard()
            .padding(.horizontal)
        }
    }

    private func loadSavedLocations() async {
        do {
            savedLocations = try await apiClient.fetchSavedLocations()
        } catch {
            print("[HomeView] Failed to load saved locations: \(error)")
        }
    }
}
