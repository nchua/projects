import SwiftUI

/// Calendar tab: shows synced calendar events with monitoring toggles.
struct CalendarView: View {
    @Environment(APIClient.self) private var apiClient
    @State private var viewModel = CalendarViewModel()

    var body: some View {
        Group {
            if !viewModel.isCalendarAuthorized {
                CalendarSyncPromptView {
                    Task { await viewModel.requestCalendarAccess() }
                }
            } else if viewModel.events.isEmpty {
                emptyState
            } else {
                eventList
            }
        }
        .navigationTitle("Calendar")
        .toolbar {
            if viewModel.isCalendarAuthorized {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await viewModel.syncCalendar(apiClient: apiClient) }
                    } label: {
                        Image(systemName: "arrow.triangle.2.circlepath")
                    }
                }
            }
        }
        .refreshable {
            await viewModel.loadEvents()
        }
        .task {
            viewModel.configure(apiClient: apiClient)
            await viewModel.loadEvents()
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar.badge.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No events with locations")
                .font(.departHeadline)
            Text("Events with physical locations will appear here for trip monitoring.")
                .font(.departCallout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .padding(.top, 60)
    }

    private var eventList: some View {
        List(viewModel.events) { event in
            CalendarEventRow(event: event) { isMonitored in
                Task {
                    await viewModel.toggleMonitoring(event: event, enabled: isMonitored)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Calendar Sync Prompt

struct CalendarSyncPromptView: View {
    let onConnect: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "calendar.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(Color.departPrimary)

            Text("Connect Your Calendar")
                .font(.departTitle2)

            Text("Depart can import events with locations and automatically create monitored trips.")
                .font(.departCallout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            Button(action: onConnect) {
                Text("Connect Calendar")
                    .font(.departHeadline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Color.departPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .padding(.horizontal, 40)
        }
        .padding(.top, 40)
    }
}

// MARK: - Calendar Event Row

struct CalendarEventRow: View {
    let event: CalendarEvent
    let onToggle: (Bool) -> Void

    @State private var isMonitored: Bool

    init(event: CalendarEvent, onToggle: @escaping (Bool) -> Void) {
        self.event = event
        self.onToggle = onToggle
        self._isMonitored = State(initialValue: event.isMonitored)
    }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(event.title)
                    .font(.departBody)

                HStack(spacing: 4) {
                    Image(systemName: "mappin")
                        .font(.system(size: 10))
                    Text(event.location)
                        .font(.departCaption)
                }
                .foregroundStyle(.secondary)

                Text(event.startDate.formatted(date: .abbreviated, time: .shortened))
                    .font(.departCaption2)
                    .foregroundStyle(.tertiary)
            }

            Spacer()

            Toggle("Monitor", isOn: $isMonitored)
                .labelsHidden()
                .tint(Color.departPrimary)
                .onChange(of: isMonitored) { _, newValue in
                    HapticManager.selection()
                    onToggle(newValue)
                }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(event.title) at \(event.location)")
        .accessibilityValue(isMonitored ? "Monitoring enabled" : "Monitoring disabled")
    }
}
