import SwiftUI

/// Alerts tab: chronological notification history across all trips.
struct AlertsView: View {
    @Environment(APIClient.self) private var apiClient
    @State private var viewModel = AlertsViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.entries.isEmpty {
                ProgressView()
                    .padding(.top, 60)
            } else if viewModel.entries.isEmpty {
                emptyState
            } else {
                alertList
            }
        }
        .navigationTitle("Alerts")
        .refreshable {
            await viewModel.loadAlerts()
        }
        .task {
            viewModel.configure(apiClient: apiClient)
            await viewModel.loadAlerts()
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "bell.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No alerts yet")
                .font(.departHeadline)
            Text("When Depart sends you departure alerts, they'll appear here.")
                .font(.departCallout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .padding(.top, 60)
    }

    private var alertList: some View {
        List(viewModel.entries) { entry in
            NavigationLink(value: DeepLinkDestination.tripDetail(entry.tripId)) {
                AlertEntryRow(entry: entry)
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Alert Entry Row

struct AlertEntryRow: View {
    let entry: AlertEntry

    var body: some View {
        HStack(spacing: 12) {
            // Tier dot
            Circle()
                .fill(entry.tierColor)
                .frame(width: 10, height: 10)

            VStack(alignment: .leading, spacing: 4) {
                Text(entry.title)
                    .font(.departBody)
                    .lineLimit(1)

                Text(entry.body)
                    .font(.departCaption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                HStack(spacing: 8) {
                    Text(entry.tripName)
                        .font(.departCaption2)
                        .foregroundStyle(Color.departPrimary)

                    Text(entry.sentAt.formatted(date: .abbreviated, time: .shortened))
                        .font(.departCaption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(entry.title) for \(entry.tripName)")
        .accessibilityValue(entry.body)
    }
}
