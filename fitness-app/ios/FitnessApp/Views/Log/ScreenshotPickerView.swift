import SwiftUI
import PhotosUI
import UIKit

struct ScreenshotPickerView: View {
    @Binding var isPresented: Bool
    let onImagesSelected: ([Data]) -> Void

    @State private var selectedItems: [PhotosPickerItem] = []
    @State private var showCamera = false
    @State private var showPhotosPicker = false
    @State private var isLoading = false
    @State private var loadedCount = 0
    @State private var totalToLoad = 0

    var body: some View {
        NavigationStack {
            ZStack {
                VoidBackground(showGrid: true, glowIntensity: 0.05)

                VStack(spacing: 32) {
                    Spacer()

                    // Header
                    VStack(spacing: 12) {
                        Text("[ SYSTEM ]")
                            .font(.ariseMono(size: 11, weight: .medium))
                            .foregroundColor(.systemPrimary)
                            .tracking(2)

                        ZStack {
                            Circle()
                                .fill(Color.systemPrimary.opacity(0.05))
                                .frame(width: 100, height: 100)

                            Circle()
                                .fill(Color.systemPrimary.opacity(0.1))
                                .frame(width: 70, height: 70)

                            Image(systemName: "camera.viewfinder")
                                .font(.system(size: 32))
                                .foregroundColor(.systemPrimary)
                                .shadow(color: .systemPrimaryGlow, radius: 10, x: 0, y: 0)
                        }

                        Text("SCAN QUEST LOG")
                            .font(.ariseHeader(size: 20, weight: .bold))
                            .foregroundColor(.textPrimary)
                            .tracking(1)

                        Text("Upload screenshots from your fitness app.\nSelect multiple to combine into one workout.")
                            .font(.ariseBody(size: 14))
                            .foregroundColor(.textSecondary)
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                    }

                    Spacer()

                    // Action Buttons
                    VStack(spacing: 16) {
                        // Camera Button
                        Button {
                            showCamera = true
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "camera.fill")
                                    .font(.system(size: 16))
                                Text("TAKE PHOTO")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 52)
                            .background(Color.voidMedium)
                            .foregroundColor(.textPrimary)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.ariseBorder, lineWidth: 1)
                            )
                        }

                        // Photo Library Button - Multi-select
                        PhotosPicker(
                            selection: $selectedItems,
                            maxSelectionCount: 10,
                            matching: .images,
                            photoLibrary: .shared()
                        ) {
                            HStack(spacing: 12) {
                                Image(systemName: "photo.on.rectangle.angled")
                                    .font(.system(size: 16))
                                Text("SELECT SCREENSHOTS")
                                    .font(.ariseHeader(size: 14, weight: .semibold))
                                    .tracking(2)
                            }
                            .frame(maxWidth: .infinity)
                            .frame(height: 52)
                            .background(Color.systemPrimary)
                            .foregroundColor(.voidBlack)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.systemPrimary, lineWidth: 2)
                            )
                            .shadow(color: .systemPrimaryGlow, radius: 15, x: 0, y: 0)
                        }
                    }
                    .padding(.horizontal, 24)

                    Spacer()
                        .frame(height: 80)
                }

                // Loading overlay
                if isLoading {
                    Color.black.opacity(0.7)
                        .ignoresSafeArea()

                    VStack(spacing: 16) {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .systemPrimary))
                            .scaleEffect(1.5)

                        Text(totalToLoad > 1 ? "LOADING IMAGES (\(loadedCount)/\(totalToLoad))..." : "LOADING IMAGE...")
                            .font(.ariseMono(size: 12, weight: .medium))
                            .foregroundColor(.textSecondary)
                            .tracking(1)
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        isPresented = false
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "xmark")
                                .font(.system(size: 14, weight: .semibold))
                            Text("CANCEL")
                                .font(.ariseMono(size: 12, weight: .medium))
                                .tracking(1)
                        }
                        .foregroundColor(.textMuted)
                    }
                }
            }
            .toolbarBackground(Color.voidBlack, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
        }
        .onChange(of: selectedItems) { _, newItems in
            if !newItems.isEmpty {
                loadImages(from: newItems)
            }
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraView { imageData in
                processSingleImage(imageData)
            }
        }
    }

    private func loadImages(from items: [PhotosPickerItem]) {
        isLoading = true
        loadedCount = 0
        totalToLoad = items.count

        Task {
            var loadedImages: [Data] = []

            for item in items {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    if let compressedData = compressImage(data, maxSizeKB: 1024) {
                        loadedImages.append(compressedData)
                    }
                }
                await MainActor.run {
                    loadedCount += 1
                }
            }

            await MainActor.run {
                isLoading = false
                selectedItems = []
                if !loadedImages.isEmpty {
                    onImagesSelected(loadedImages)
                    isPresented = false
                }
            }
        }
    }

    private func processSingleImage(_ data: Data) {
        // Compress image if needed (max 1MB)
        if let compressedData = compressImage(data, maxSizeKB: 1024) {
            onImagesSelected([compressedData])
            isPresented = false
        }
    }

    private func compressImage(_ data: Data, maxSizeKB: Int) -> Data? {
        guard let image = UIImage(data: data) else { return nil }

        let maxBytes = maxSizeKB * 1024
        var compression: CGFloat = 1.0
        var imageData = image.jpegData(compressionQuality: compression)

        while let data = imageData, data.count > maxBytes, compression > 0.1 {
            compression -= 0.1
            imageData = image.jpegData(compressionQuality: compression)
        }

        return imageData
    }
}

// MARK: - Camera View

struct CameraView: UIViewControllerRepresentable {
    let onImageCaptured: (Data) -> Void
    @Environment(\.dismiss) var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraView

        init(_ parent: CameraView) {
            self.parent = parent
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey : Any]) {
            if let image = info[.originalImage] as? UIImage,
               let data = image.jpegData(compressionQuality: 0.8) {
                parent.onImageCaptured(data)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
