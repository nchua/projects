import MapKit
import SwiftUI

/// Location search result for the add trip form.
struct LocationResult: Hashable {
    let name: String
    let address: String
    let coordinate: CLLocationCoordinate2D

    func hash(into hasher: inout Hasher) {
        hasher.combine(name)
        hasher.combine(address)
        hasher.combine(coordinate.latitude)
        hasher.combine(coordinate.longitude)
    }

    static func == (lhs: LocationResult, rhs: LocationResult) -> Bool {
        lhs.name == rhs.name && lhs.address == rhs.address
            && lhs.coordinate.latitude == rhs.coordinate.latitude
            && lhs.coordinate.longitude == rhs.coordinate.longitude
    }
}

/// Full-screen location search with autocomplete.
struct LocationSearchView: View {
    let title: String
    let savedLocations: [SavedLocation]
    let onSelect: (LocationResult) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var searchText = ""
    @State private var completer = LocationSearchCompleter()
    @State private var isGeocoding = false

    var body: some View {
        NavigationStack {
            List {
                // Saved Locations
                if !savedLocations.isEmpty && searchText.isEmpty {
                    Section {
                        ForEach(savedLocations) { location in
                            Button {
                                onSelect(LocationResult(
                                    name: location.name,
                                    address: location.address,
                                    coordinate: CLLocationCoordinate2D(
                                        latitude: location.latitude,
                                        longitude: location.longitude
                                    )
                                ))
                                dismiss()
                            } label: {
                                Label {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(location.name)
                                            .font(.departBody)
                                            .foregroundStyle(Color.departTextPrimary)
                                        Text(location.address)
                                            .font(.departCaption)
                                            .foregroundStyle(Color.departTextSecondary)
                                            .lineLimit(1)
                                    }
                                } icon: {
                                    Image(systemName: location.icon ?? "mappin.circle.fill")
                                        .foregroundStyle(Color.departPrimary)
                                }
                            }
                        }
                    } header: {
                        Text("Saved Locations")
                    }
                }

                // Search Results
                if !completer.results.isEmpty {
                    Section {
                        ForEach(completer.results, id: \.self) { result in
                            Button {
                                selectCompletion(result)
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(result.title)
                                        .font(.departBody)
                                        .foregroundStyle(Color.departTextPrimary)
                                    Text(result.subtitle)
                                        .font(.departCaption)
                                        .foregroundStyle(Color.departTextSecondary)
                                        .lineLimit(1)
                                }
                            }
                        }
                    } header: {
                        Text("Search Results")
                    }
                }

                // Empty state
                if completer.results.isEmpty && !searchText.isEmpty && !isGeocoding {
                    ContentUnavailableView(
                        "No Results",
                        systemImage: "magnifyingglass",
                        description: Text("Try a different search term")
                    )
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $searchText, prompt: "Search for a place")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .overlay {
                if isGeocoding {
                    ProgressView("Finding location...")
                        .padding()
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .onChange(of: searchText) { _, newValue in
                completer.search(query: newValue)
            }
        }
    }

    private func selectCompletion(_ completion: MKLocalSearchCompletion) {
        isGeocoding = true
        Task {
            defer { isGeocoding = false }
            let request = MKLocalSearch.Request(completion: completion)
            let search = MKLocalSearch(request: request)
            do {
                let response = try await search.start()
                if let item = response.mapItems.first {
                    let result = LocationResult(
                        name: item.name ?? completion.title,
                        address: [item.placemark.thoroughfare, item.placemark.locality]
                            .compactMap { $0 }
                            .joined(separator: ", "),
                        coordinate: item.placemark.coordinate
                    )
                    onSelect(result)
                    dismiss()
                }
            } catch {
                print("[LocationSearch] Geocode error: \(error)")
            }
        }
    }
}

// MARK: - MKLocalSearchCompleter Wrapper

@Observable
final class LocationSearchCompleter: NSObject, MKLocalSearchCompleterDelegate {
    var results: [MKLocalSearchCompletion] = []
    private let completer = MKLocalSearchCompleter()

    override init() {
        super.init()
        completer.delegate = self
        completer.resultTypes = [.address, .pointOfInterest]
    }

    func search(query: String) {
        if query.isEmpty {
            results = []
            return
        }
        completer.queryFragment = query
    }

    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        results = completer.results
    }

    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) {
        print("[LocationSearchCompleter] Error: \(error)")
    }
}
