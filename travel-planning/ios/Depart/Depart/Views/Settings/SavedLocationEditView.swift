import MapKit
import SwiftUI

/// Edit or add a saved location: name, icon, address search, map preview.
struct SavedLocationEditView: View {
    let location: SavedLocation?
    let onSave: () async -> Void

    @Environment(APIClient.self) private var apiClient
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var icon: String = "📍"
    @State private var address: String = ""
    @State private var latitude: Double = 0
    @State private var longitude: Double = 0
    @State private var showLocationSearch = false
    @State private var isSaving = false
    @State private var error: String?

    private let iconOptions = ["🏠", "🏢", "🏋️", "🏫", "🏥", "🛒", "✈️", "⛪", "🎭", "📍"]

    var body: some View {
        Form {
            Section("Name") {
                TextField("Location name", text: $name)
            }

            Section("Icon") {
                LazyVGrid(columns: Array(repeating: .init(.flexible()), count: 5), spacing: 12) {
                    ForEach(iconOptions, id: \.self) { emoji in
                        Button {
                            HapticManager.selection()
                            icon = emoji
                        } label: {
                            Text(emoji)
                                .font(.title2)
                                .frame(width: 44, height: 44)
                                .background(icon == emoji ? Color.departPrimary.opacity(0.15) : Color.clear)
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Section("Address") {
                Button {
                    showLocationSearch = true
                } label: {
                    HStack {
                        Text(address.isEmpty ? "Search for address..." : address)
                            .foregroundStyle(address.isEmpty ? .secondary : .primary)
                            .lineLimit(2)
                        Spacer()
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(.secondary)
                    }
                }

                if latitude != 0 && longitude != 0 {
                    Map(initialPosition: .region(MKCoordinateRegion(
                        center: CLLocationCoordinate2D(latitude: latitude, longitude: longitude),
                        span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                    ))) {
                        Marker(name, coordinate: CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
                    }
                    .frame(height: 150)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .disabled(true)
                }
            }

            if let error {
                Section {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.departCaption)
                }
            }
        }
        .navigationTitle(location == nil ? "Add Location" : "Edit Location")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    Task { await save() }
                }
                .disabled(name.isEmpty || address.isEmpty || isSaving)
            }
        }
        .sheet(isPresented: $showLocationSearch) {
            LocationSearchView(title: "Search Address", savedLocations: []) { result in
                address = result.address
                latitude = result.coordinate.latitude
                longitude = result.coordinate.longitude
                if name.isEmpty {
                    name = result.name
                }
            }
        }
        .onAppear {
            if let location {
                name = location.name
                icon = location.icon ?? "📍"
                address = location.address
                latitude = location.latitude
                longitude = location.longitude
            }
        }
    }

    private func save() async {
        isSaving = true
        error = nil

        do {
            if let location {
                let update = UpdateSavedLocationRequest(
                    name: name,
                    address: address,
                    latitude: latitude,
                    longitude: longitude,
                    icon: icon
                )
                _ = try await apiClient.updateSavedLocation(locationId: location.id, update)
            } else {
                let request = CreateSavedLocationRequest(
                    name: name,
                    address: address,
                    latitude: latitude,
                    longitude: longitude,
                    icon: icon,
                    sortOrder: 0
                )
                _ = try await apiClient.createSavedLocation(request)
            }
            HapticManager.success()
            await onSave()
            dismiss()
        } catch {
            self.error = error.localizedDescription
            HapticManager.error()
        }

        isSaving = false
    }
}
