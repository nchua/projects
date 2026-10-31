import FilmCore
import Foundation
import ImageIO
import Observation
import Photos
import PhotosUI
import UIKit
import UniformTypeIdentifiers

/// One photo, picked or taken, from loading through rendering to saving.
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
    /// A photo taken in the app keeps its DNG until it is saved (as its own asset, beside the render) or cleared.
    var original: URL?

    init(name: String) { self.name = name }

    var rendered: Rendered? {
        if case .done(let r) = status { r } else { nil }
    }
}

/// The batch: picked and taken photos queue in order and render one at a time; Cancel skips everything still queued.
@MainActor @Observable
final class Session {
    /// Where a photo comes from: the picker's item provider, or a DNG the in-app camera wrote.
    enum Source {
        case picked(NSItemProvider)
        case captured(URL)
    }

    var items: [Item] = []
    var isRunning = false
    var photosDenied = false
    var fatalError: String?

    private var queue: [(Item, Source)] = []
    private var renderer: Renderer?
    private let root = FileManager.default.temporaryDirectory.appendingPathComponent("Print", isDirectory: true)

    var canSaveAll: Bool { items.contains(where: \.isSavable) }

    init() {
        do { renderer = try Renderer() } catch { fatalError = "\(error)" }
    }

    func pick(_ results: [PHPickerResult]) {
        enqueue(results.map { (Item(name: $0.itemProvider.suggestedName ?? "Photo"), .picked($0.itemProvider)) })
    }

    /// A DNG the camera just wrote (into `captureDirectory()`).
    func add(captured url: URL) {
        enqueue([(Item(name: url.deletingPathExtension().lastPathComponent), .captured(url))])
    }

    /// The camera writes its DNGs here; `clear()` removes them with everything else.
    func captureDirectory() throws -> URL {
        let dir = root.appendingPathComponent("captures", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func enqueue(_ new: [(Item, Source)]) {
        items.append(contentsOf: new.map(\.0))
        queue.append(contentsOf: new)
        guard !isRunning else { return }   // the running worker picks these up
        isRunning = true
        Task { await drain() }
    }

    func cancel() {
        for (item, _) in queue { item.status = .skipped("Cancelled") }
        queue.removeAll()
    }

    func clear() {
        guard !isRunning, !items.contains(where: \.isSaving) else { return }
        items.removeAll()
        try? FileManager.default.removeItem(at: root)
    }

    /// The single worker: takes queued items in pick order until the queue is empty.
    private func drain() async {
        defer { isRunning = false }
        guard let renderer else { return }
        while !queue.isEmpty {
            let (item, source) = queue.removeFirst()
            item.status = .rendering
            do {
                let dir = root.appendingPathComponent(item.id.uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let rendered: Rendered
                switch source {
                case .picked(let provider):
                    let dng = try await Self.loadRaw(provider, into: dir)
                    defer { try? FileManager.default.removeItem(at: dng) }   // the library has the original
                    rendered = try await renderer.render(dng: dng, into: dir)
                case .captured(let dng):
                    item.original = dng   // kept until Save or Clear: the library has nothing yet
                    rendered = try await renderer.render(dng: dng, into: dir)
                }
                item.thumbnail = Self.thumbnail(rendered.renderURL)
                item.status = .done(rendered)
            } catch {
                item.status = .skipped(Self.describe(error, source))
            }
        }
    }

    /// The skip reason; Debug builds add the types the picker offered, to diagnose skips on device.
    nonisolated static func describe(_ error: Error, _ source: Source) -> String {
        #if DEBUG
        if case .picked(let provider) = source {
            return "\(error) [\(provider.registeredTypeIdentifiers.joined(separator: ", "))]"
        }
        #endif
        return "\(error)"
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

    /// Saves the render and, for a photo taken here, its ProRAW as its own asset (like the Camera app's) in the
    /// same change. A taken photo whose render was skipped still saves its ProRAW: the capture is never lost
    /// to the pipeline.
    func save(_ item: Item) async {
        let (r, original) = (item.rendered, item.original)
        guard r != nil || original != nil else { return }
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else {
            photosDenied = true
            return
        }
        item.save = .saving
        let date = r?.captureDate ?? original.flatMap(Self.captureDate)
        do {
            try await PHPhotoLibrary.shared().performChanges {
                if let original {
                    let raw = PHAssetCreationRequest.forAsset()
                    raw.addResource(with: .photo, fileURL: original, options: nil)
                    raw.creationDate = date
                    raw.location = r?.location
                }
                if let r {
                    let request = PHAssetCreationRequest.forAsset()
                    request.addResource(with: .photo, fileURL: r.renderURL, options: nil)
                    request.creationDate = date
                    request.location = r.location
                }
            }
            if let original {   // Photos has it now
                try? FileManager.default.removeItem(at: original)
                item.original = nil
            }
            item.save = .saved
        } catch {
            item.save = .failed(error.localizedDescription)
        }
    }

    /// The capture time of a DNG on disk, for a taken photo whose render was skipped.
    nonisolated static func captureDate(_ url: URL) -> Date? {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any] else { return nil }
        return Encoder.captureDate(props)
    }
}

extension Item {
    var isSaved: Bool {
        if case .saved = save { true } else { false }
    }

    var isSaving: Bool {
        if case .saving = save { true } else { false }
    }

    /// A render, or a taken photo's ProRAW, that isn't in the library yet.
    var isSavable: Bool { (rendered != nil || original != nil) && !isSaved }
}
