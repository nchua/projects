import SwiftUI

struct ContentView: View {
    @State private var session = Session()
    @State private var camera = Camera()
    @State private var showPicker = false
    @State private var showCamera = false
    @State private var viewing: Item?

    var body: some View {
        NavigationStack {
            Group {
                if let error = session.fatalError {
                    ContentUnavailableView("Can't load the film model", systemImage: "exclamationmark.triangle",
                                           description: Text(error))
                } else if session.items.isEmpty {
                    ContentUnavailableView {
                        Label("No photos", image: .printMark)
                            .symbolRenderingMode(.hierarchical)
                    } description: {
                        Text("Take a ProRAW photo, or pick ones from your library, to develop them.")
                    } actions: {
                        // Text only: the labels say it, and the print above is the one picture here. The size
                        // goes inside: ContentUnavailableView sets its own control size for its actions.
                        Group {
                            Button("Take Photo") { showCamera = true }
                                .buttonStyle(.borderedProminent)
                            Button("Pick Photos") { showPicker = true }
                                .buttonStyle(.bordered)
                        }
                        .controlSize(.large)
                    }
                } else {
                    List(session.items) { item in
                        ItemRow(item: item) { Task { await session.save(item) } }
                            .contentShape(Rectangle())
                            .onTapGesture { if item.rendered != nil { viewing = item } }
                    }
                    .listStyle(.plain)
                }
            }
            .background(Color.black)
            .navigationTitle("Print")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if session.isRunning {
                        Button("Cancel", role: .cancel) { session.cancel() }
                    } else if !session.items.isEmpty {
                        Button("Clear") { session.clear() }
                    }
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if session.canSaveAll && !session.isRunning {
                        Button("Save All") { Task { await session.saveAll() } }
                    }
                    Button("Take Photo", systemImage: "camera") { showCamera = true }
                    Button("Pick Photos", image: .printNegative) { showPicker = true }
                }
            }
            .sheet(isPresented: $showPicker) {
                PhotoPicker { session.pick($0) }
                    .ignoresSafeArea()
            }
            .fullScreenCover(isPresented: $showCamera) {
                CameraView(session: session, camera: camera)
            }
            .fullScreenCover(item: $viewing) { item in
                if let r = item.rendered { ViewerView(rendered: r) }
            }
            .alert("Photos access is off", isPresented: $session.photosDenied) {
                Button("Open Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                }
                Button("Not Now", role: .cancel) {}
            } message: {
                Text("Allow Print to add photos in Settings to save your renders.")
            }
        }
    }
}

struct ItemRow: View {
    let item: Item
    let onSave: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            thumbnail
                .frame(width: 60, height: 80)
                .clipShape(RoundedRectangle(cornerRadius: 4))
            VStack(alignment: .leading, spacing: 4) {
                Text(item.name).font(.headline)
                detail.font(.footnote).foregroundStyle(.secondary)
                if case .failed(let message) = item.save {
                    Text("Save failed: \(message)").font(.footnote).foregroundStyle(.red)
                }
            }
            Spacer()
            saveButton
                .buttonStyle(.bordered)
                .controlSize(.large)
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder private var thumbnail: some View {
        if let image = item.thumbnail {
            Image(uiImage: image).resizable().scaledToFill()
        } else {
            Rectangle().fill(Color.white.opacity(0.08))
                .overlay { if case .rendering = item.status { ProgressView() } }
        }
    }

    @ViewBuilder private var detail: some View {
        switch item.status {
        case .waiting: Text("Waiting")
        case .rendering: Text("Developing…")
        case .skipped(let reason):
            Text(item.original == nil ? reason : "\(reason) — the ProRAW can still be saved")
        case .done(let r):
            #if DEBUG
            Text(String(format: "%.0f MP · %@ · decode %.2f s · film %.2f s · encode %.2f s · peak %d MB",
                        r.megapixels, r.metering, r.decodeSeconds, r.filmSeconds, r.encodeSeconds,
                        Int(r.peakFootprint >> 20)))
            #else
            Text(r.captureDate?.formatted(date: .abbreviated, time: .shortened) ?? "Developed")
            #endif
        }
    }

    @ViewBuilder private var saveButton: some View {
        if item.isSavable || item.isSaved {
            switch item.save {
            case .unsaved: Button("Save", action: onSave)
            case .saving: ProgressView()
            case .saved: Text("Saved").font(.subheadline).foregroundStyle(.secondary)
            case .failed:
                Button("Retry", action: onSave)
            }
        }
    }
}
