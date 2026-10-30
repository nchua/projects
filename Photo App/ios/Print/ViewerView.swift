import SwiftUI

/// Full-screen render; press and hold to see Apple's own rendering (the DNG's embedded SDR preview).
struct ViewerView: View {
    let rendered: Rendered
    @Environment(\.dismiss) private var dismiss
    @State private var showApple = false
    @State private var render: UIImage?
    @State private var apple: UIImage?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let image = showApple ? apple : render {
                Image(uiImage: image).resizable().scaledToFit()
            }
        }
        .overlay(alignment: .bottom) {
            Text(showApple ? "Apple (SDR preview)" : rendered.comparisonURL == nil ? "Print" : "Print · hold for Apple")
                .font(.footnote).padding(8).background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 24)
        }
        .overlay(alignment: .topTrailing) {
            Button("Done") { dismiss() }.buttonStyle(.bordered).padding()
        }
        .task {
            // Decode both once; pressing only swaps which one is shown
            render = UIImage(contentsOfFile: rendered.renderURL.path)
            apple = rendered.comparisonURL.flatMap { UIImage(contentsOfFile: $0.path) }
        }
        .onLongPressGesture(minimumDuration: 0.15, perform: {}, onPressingChanged: { pressing in
            showApple = pressing && rendered.comparisonURL != nil
        })
    }
}
