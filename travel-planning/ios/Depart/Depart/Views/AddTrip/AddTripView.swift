import SwiftUI

/// Trip creation form: name, from/to, arrival time, buffer.
struct AddTripView: View {
    @Environment(APIClient.self) private var apiClient
    @Environment(\.dismiss) private var dismiss
    @State private var viewModel = AddTripViewModel()

    let savedLocations: [SavedLocation]
    var onSaved: (() -> Void)?

    var body: some View {
        NavigationStack {
            Form {
                // Trip Name
                Section {
                    TextField("Trip name (optional)", text: $viewModel.name)
                        .font(.departBody)
                } header: {
                    Text("Name")
                }

                // Locations
                Section {
                    // Origin
                    Button {
                        viewModel.showOriginSearch = true
                    } label: {
                        HStack {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 8))
                                .foregroundStyle(Color.departPrimary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("From")
                                    .font(.departCaption)
                                    .foregroundStyle(Color.departTextSecondary)
                                Text(viewModel.origin?.name ?? "Choose origin")
                                    .font(.departBody)
                                    .foregroundStyle(
                                        viewModel.origin != nil
                                            ? Color.departTextPrimary
                                            : Color.departTextSecondary
                                    )
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                    }

                    // Destination
                    Button {
                        viewModel.showDestSearch = true
                    } label: {
                        HStack {
                            Image(systemName: "mappin.circle.fill")
                                .font(.system(size: 12))
                                .foregroundStyle(Color.departRed)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("To")
                                    .font(.departCaption)
                                    .foregroundStyle(Color.departTextSecondary)
                                Text(viewModel.destination?.name ?? "Choose destination")
                                    .font(.departBody)
                                    .foregroundStyle(
                                        viewModel.destination != nil
                                            ? Color.departTextPrimary
                                            : Color.departTextSecondary
                                    )
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                    }
                } header: {
                    Text("Route")
                }

                // Arrival Time
                Section {
                    DatePicker(
                        "Arrive by",
                        selection: $viewModel.arrivalDate,
                        in: Date()...,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                    .font(.departBody)
                } header: {
                    Text("Timing")
                }

                // Buffer
                Section {
                    StepperControlView(
                        "Buffer time",
                        value: $viewModel.bufferMinutes,
                        in: 0...60,
                        step: 5,
                        unit: "min"
                    )
                } header: {
                    Text("Buffer")
                } footer: {
                    Text("Extra time added to your departure for parking, walking, etc.")
                }

                // Route Estimate (if available)
                if let estimate = viewModel.routeEstimateMinutes {
                    Section {
                        HStack {
                            Image(systemName: "car.fill")
                                .foregroundStyle(Color.departPrimary)
                            Text("Estimated \(estimate) min drive")
                                .font(.departBody)
                            Spacer()
                            if let departureTime = computeDepartureTime(travelMinutes: estimate) {
                                Text("Leave by \(departureTime.shortTimeString)")
                                    .font(.departCaption)
                                    .foregroundStyle(Color.departTextSecondary)
                            }
                        }
                    }
                }

                // Error
                if let error = viewModel.error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.departCaption)
                    }
                }
            }
            .navigationTitle("Add Trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            if await viewModel.saveTrip() {
                                onSaved?()
                                dismiss()
                            }
                        }
                    }
                    .disabled(!viewModel.isValid || viewModel.isSaving)
                    .fontWeight(.semibold)
                }
            }
            .sheet(isPresented: $viewModel.showOriginSearch) {
                LocationSearchView(
                    title: "From",
                    savedLocations: savedLocations
                ) { result in
                    viewModel.origin = result
                    Task { await viewModel.estimateRoute() }
                }
            }
            .sheet(isPresented: $viewModel.showDestSearch) {
                LocationSearchView(
                    title: "To",
                    savedLocations: savedLocations
                ) { result in
                    viewModel.destination = result
                    Task { await viewModel.estimateRoute() }
                }
            }
            .onAppear {
                viewModel.configure(apiClient: apiClient, savedLocations: savedLocations)
            }
        }
    }

    private func computeDepartureTime(travelMinutes: Int) -> Date? {
        let totalMinutes = travelMinutes + viewModel.bufferMinutes
        return viewModel.arrivalDate.addingTimeInterval(-TimeInterval(totalMinutes * 60))
    }
}
