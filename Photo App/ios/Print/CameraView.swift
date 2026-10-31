import AVFoundation
import SwiftUI

/// The viewfinder: Apple's live preview (not the look), a shutter, and the renders developing behind it.
struct CameraView: View {
    let session: Session
    let camera: Camera
    @Environment(\.dismiss) private var dismiss
    @State private var captureError: String?

    private var developing: Int {
        session.items.filter { if case .done = $0.status { false } else if case .skipped = $0.status { false } else { true } }.count
    }
    private var lastThumbnail: UIImage? { session.items.last(where: { $0.thumbnail != nil })?.thumbnail }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            switch camera.state {
            case .idle, .starting:
                ProgressView().tint(.white)
            case .ready:
                CameraPreview(layer: camera.previewLayer).ignoresSafeArea()
            case .unavailable(let reason):
                ContentUnavailableView {
                    Label("Camera unavailable", systemImage: "camera.badge.ellipsis")
                } description: {
                    Text(reason).accessibilityIdentifier("camera-unavailable-reason")
                } actions: {
                    if camera.canOpenSettings {
                        Button("Open Settings") {
                            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
            }
        }
        .overlay(alignment: .top) {
            HStack {
                Button("Done") { dismiss() }.buttonStyle(.bordered)
                Spacer()
                Text(camera.formatLabel).font(.footnote).foregroundStyle(.secondary)
            }
            .padding()
        }
        .overlay(alignment: .bottom) {
            if camera.state == .ready { controls.padding(.bottom, 32) }
        }
        .task { await camera.start() }
        .onDisappear { camera.stop() }
        .alert("Couldn't take the photo", isPresented: Binding(get: { captureError != nil }, set: { if !$0 { captureError = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(captureError ?? "")
        }
    }

    private var controls: some View {
        HStack {
            Button { dismiss() } label: {
                if let image = lastThumbnail {
                    Image(uiImage: image).resizable().scaledToFill()
                        .frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: 8))
                } else {
                    RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.08)).frame(width: 56, height: 56)
                        .overlay { if developing > 0 { ProgressView().tint(.white) } }
                }
            }
            .accessibilityLabel("Show renders")
            .overlay(alignment: .topTrailing) {
                if developing > 0 {
                    Text("\(developing)").font(.caption2.bold()).padding(5)
                        .background(Color.orange, in: Circle()).offset(x: 6, y: -6)
                }
            }
            Spacer()
            Button(action: take) {
                Circle().fill(.white).frame(width: 68, height: 68)
                    .overlay(Circle().stroke(.white.opacity(0.5), lineWidth: 3).frame(width: 82, height: 82))
            }
            .accessibilityLabel("Shutter")
            .disabled(camera.isCapturing)
            .opacity(camera.isCapturing ? 0.4 : 1)
            Spacer()
            Color.clear.frame(width: 56, height: 56)
        }
        .padding(.horizontal, 32)
    }

    private func take() {
        Task {
            do {
                let url = try await camera.capture(into: try session.captureDirectory())
                session.add(captured: url)
            } catch {
                captureError = (error as? CameraError)?.description ?? error.localizedDescription
            }
        }
    }
}

/// Hosts the camera's preview layer and keeps it sized to the view.
struct CameraPreview: UIViewRepresentable {
    let layer: AVCaptureVideoPreviewLayer

    func makeUIView(context: Context) -> PreviewHost {
        let view = PreviewHost()
        view.layer.addSublayer(layer)
        view.preview = layer
        return view
    }

    func updateUIView(_ view: PreviewHost, context: Context) {}

    final class PreviewHost: UIView {
        var preview: AVCaptureVideoPreviewLayer?
        override func layoutSubviews() {
            super.layoutSubviews()
            preview?.frame = bounds
        }
    }
}
