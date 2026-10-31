import FilmCore
import Foundation
import ImageIO
import Observation
import Photos
import PhotosUI
import UIKit
import UniformTypeIdentifiers

/// One picked photo, from loading through rendering to saving.
@MainActor @Observable
final class Item: Identifiable {
    enum Status {
        case waiting
        case rendering
        case done(Rendered)
        case skipped(String)
    }

    enum SaveState { case unsaved, saving, saved, failed(String) }

    let id = UUID()
    let name: String
    var status: Status = .waiting
    var save: SaveState = .unsaved
    /// Small preview for the list, made once from the render (not the full 6 MP JPEG per row).
    var thumbnail: UIImage?

    init(name: String) { self.name = name }

    var rendered: Rendered? {
        if case .done(let r) = status { r } else { nil }
    }
}

/// The batch: picks queue in order and render one at a time; Cancel skips everything still queued.
@MainActor @Observable
final class Session {
    var items: [Item] = []
    var isRunning = false
    var photosDenied = false
    var fatalError: String?

    private var queue: [(Item, NSItemProvider)] = []
    private var renderer: Renderer?
    private let root = FileManager.default.temporaryDirectory.appendingPathComponent("Print", isDirectory: true)

    var canSaveAll: Bool { items.contains(where: \.isSavable) }

    init() {
        do { renderer = try Renderer() } catch { fatalError = "\(error)" }
    }

    func pick(_ results: [PHPickerResult]) {
        let picked = results.map { (Item(name: $0.itemProvider.suggestedName ?? "Photo"), $0.itemProvider) }
        items.append(contentsOf: picked.map(\.0))
        queue.append(contentsOf: picked)
        guard !isRunning else { return }   // the running worker picks these up
        isRunning = true
        Task { await drain() }
    }

    func cancel() {
        for (item, _) in queue { item.status = .skipped("Cancelled") }
        queue.removeAll()
    }

    func clear() {
        guard !isRunning else { return }
        items.removeAll()
        try? FileManager.default.removeItem(at: root)
    }

    /// The single worker: takes queued items in pick order until the queue is empty.
    private func drain() async {
        defer { isRunning = false }
        guard let renderer else { return }
        while !queue.isEmpty {
            let (item, provider) = queue.removeFirst()
            item.status = .rendering
            do {
                let dir = root.appendingPathComponent(item.id.uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let dng = try await Self.loadRaw(provider, into: dir)
                defer { try? FileManager.default.removeItem(at: dng) }   // only the JPEGs stay
                let rendered = try await renderer.render(dng: dng, into: dir)
                item.thumbnail = Self.thumbnail(rendered.renderURL)
                item.status = .done(rendered)
            } catch {
                item.status = .skipped(Self.describe(error, provider))
            }
        }
    }

    /// The skip reason; Debug builds add the types the picker offered, to diagnose skips on device.
    nonisolated static func describe(_ error: Error, _ provider: NSItemProvider) -> String {
        #if DEBUG
        "\(error) [\(provider.registeredTypeIdentifiers.joined(separator: ", "))]"
        #else
        "\(error)"
        #endif
    }

    /// ImageIO's subsampled decode, so the list never holds full-size bitmaps.
    nonisolated static func thumbnail(_ url: URL) -> UIImage? {
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                        kCGImageSourceThumbnailMaxPixelSize: 240]
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(src, 0, options as CFDictionary) else { return nil }
        return UIImage(cgImage: image)
    }

    /// Copies the picked item's RAW file into `dir` (the provider's file is deleted when the callback returns).
    nonisolated static func loadRaw(_ provider: NSItemProvider, into dir: URL) async throws -> URL {
        let raw = UTType.rawImage.identifier
        guard provider.hasItemConformingToTypeIdentifier(raw) else { throw DecodeError.notProRAW }
        return try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadFileRepresentation(forTypeIdentifier: raw) { url, error in
                guard let url else {
                    continuation.resume(throwing: error ?? DecodeError.unreadable)
                    return
                }
                let copy = dir.appendingPathComponent(url.lastPathComponent)
                do {
                    try FileManager.default.copyItem(at: url, to: copy)
                    continuation.resume(returning: copy)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    // MARK: Saving

    func saveAll() async {
        for item in items where item.isSavable { await save(item) }
    }

    func save(_ item: Item) async {
        guard let r = item.rendered else { return }
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else {
            photosDenied = true
            return
        }
        item.save = .saving
        do {
            try await PHPhotoLibrary.shared().performChanges {
                let request = PHAssetCreationRequest.forAsset()
                request.addResource(with: .photo, fileURL: r.renderURL, options: nil)
                request.creationDate = r.captureDate
                request.location = r.location
            }
            item.save = .saved
        } catch {
            item.save = .failed(error.localizedDescription)
        }
    }
}

extension Item {
    var isSaved: Bool {
        if case .saved = save { true } else { false }
    }

    var isSavable: Bool { rendered != nil && !isSaved }
}
