import AVFoundation
import Foundation
import Observation
import UIKit

enum CameraError: Error, CustomStringConvertible {
    case noCamera, noProRAW, denied, notReady, configuration(String), noData

    var description: String {
        switch self {
        case .noCamera: "No camera on this device"
        case .noProRAW: "This camera can't shoot ProRAW"
        case .denied: "Camera access is off. Allow it in Settings to take photos."
        case .notReady: "The camera isn't ready"
        case .configuration(let what): "Couldn't set up the camera (\(what))"
        case .noData: "The camera returned no photo"
        }
    }
}

/// The in-app camera (APP_SPEC.md §5.4, M6): the back wide camera, Apple ProRAW at the sensor-binned size,
/// DNG only. `capture()` writes the DNG into a directory and returns its URL; `Session` then develops it
/// exactly like a picked file, so the look is the same whichever way a photo arrives. One instance lives as
/// long as the app; the viewfinder starts and stops it.
@MainActor @Observable
final class Camera {
    enum State: Equatable { case idle, starting, ready, unavailable(String) }

    /// The Camera app's ProRAW default is the sensor-binned 12 MP; 48 MP is its opt-in "ProRAW Max".
    nonisolated static let captureLongSide: Int32 = 4032
    /// How much of Apple's multi-frame processing goes into the ProRAW: .speed (least), .balanced, .quality (Deep Fusion).
    nonisolated static let qualityPrioritization: AVCapturePhotoOutput.QualityPrioritization = .balanced

    private(set) var state: State = .idle
    private(set) var isCapturing = false
    /// "ProRAW 4032×3024", for the viewfinder.
    private(set) var formatLabel = ""
    /// Whether Settings can fix an unavailable camera (access the user turned off, not a policy restriction).
    private(set) var canOpenSettings = false
    /// The viewfinder's layer, made once with the camera so views allocate no AVFoundation objects.
    let previewLayer = AVCaptureVideoPreviewLayer()

    private let engine = Engine()
    private var rotation: AVCaptureDevice.RotationCoordinator?

    /// Asks for access, configures the session once, attaches the preview and starts it. A `stop()` during
    /// any wait wins: the session is left stopped and the state `.idle`.
    func start() async {
        guard state == .idle else { return }
        state = .starting
        canOpenSettings = false
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: break
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            guard state == .starting else { return }
            guard granted else { return fail(.denied, settings: true) }
        case .denied: return fail(.denied, settings: true)
        default: return fail(.denied, settings: false)   // restricted by policy
        }
        do {
            let (device, label) = try await engine.configureIfNeeded()
            guard state == .starting else { return }
            if previewLayer.session == nil {   // attached before the session first runs
                previewLayer.session = engine.session
                previewLayer.videoGravity = .resizeAspect
                previewLayer.connection?.videoRotationAngle = 90
            }
            rotation = AVCaptureDevice.RotationCoordinator(device: device, previewLayer: previewLayer)
            formatLabel = label
            await engine.run(true)
            guard state == .starting else { return await engine.run(false) }
            state = .ready
        } catch let error as CameraError {
            fail(error, settings: false)
        } catch {
            fail(.configuration(error.localizedDescription), settings: false)
        }
    }

    /// Back to `.idle` at once (the next open re-checks access and restarts); the engine stops the session as
    /// soon as any capture in flight has delivered, so leaving the viewfinder never loses a shot.
    func stop() {
        state = .idle
        Task { await engine.run(false) }
    }

    /// Takes one ProRAW photo and writes it to `dir` as `Print-<time>.dng` (the name seeds the grain, §5.2).
    func capture(into dir: URL) async throws -> URL {
        guard state == .ready, !isCapturing else { throw CameraError.notReady }
        isCapturing = true
        defer { isCapturing = false }
        let angle = rotation?.videoRotationAngleForHorizonLevelCapture ?? 90
        let data = try await engine.capture(rotationAngle: angle)
        let url = dir.appendingPathComponent("Print-\(Self.stamp(Date())).dng")
        try await Task.detached { try data.write(to: url, options: .atomic) }.value
        return url
    }

    /// `yyyyMMdd-HHmmss-SSS` in local time, always Gregorian.
    nonisolated static func stamp(_ date: Date) -> String {
        date.formatted(.verbatim("\(year: .defaultDigits)\(month: .twoDigits)\(day: .twoDigits)-\(hour: .twoDigits(clock: .twentyFourHour, hourCycle: .zeroBased))\(minute: .twoDigits)\(second: .twoDigits)-\(secondFraction: .fractional(3))",
                                 timeZone: .current, calendar: Calendar(identifier: .gregorian)))
    }

    private func fail(_ error: CameraError, settings: Bool) {
        state = .unavailable(error.description)
        canOpenSettings = settings
    }
}

/// Owns the AVFoundation objects; every call runs on its serial queue, and each capture's continuation is
/// kept there until the photo arrives or the final callback says it never will.
private final class Engine: NSObject, AVCapturePhotoCaptureDelegate, @unchecked Sendable {
    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "com.nickchua.print.camera")
    private var device: AVCaptureDevice?
    private var pending: [Int64: CheckedContinuation<Data, Error>] = [:]
    /// A stop requested while a capture was in flight; honoured when the last capture's final callback lands.
    private var stopWhenIdle = false

    /// Back wide camera, `.photo` preset, ProRAW on, the largest photo size within `Camera.captureLongSide`.
    func configureIfNeeded() async throws -> (AVCaptureDevice, String) {
        try await withCheckedThrowingContinuation { cont in
            queue.async {
                do {
                    cont.resume(returning: try self.configureLocked())
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    private func configureLocked() throws -> (AVCaptureDevice, String) {
        if let device { return (device, Self.label(output.maxPhotoDimensions)) }
        guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
            throw CameraError.noCamera
        }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .photo
        let input = try AVCaptureDeviceInput(device: camera)
        guard session.canAddInput(input) else { throw CameraError.configuration("input") }
        session.addInput(input)
        guard session.canAddOutput(output) else { throw CameraError.configuration("output") }
        session.addOutput(output)
        guard output.isAppleProRAWSupported else { throw CameraError.noProRAW }
        output.isAppleProRAWEnabled = true
        output.maxPhotoQualityPrioritization = Camera.qualityPrioritization
        let sizes = camera.activeFormat.supportedMaxPhotoDimensions
            .filter { max($0.width, $0.height) <= Camera.captureLongSide }
        guard let size = sizes.max(by: { $0.width * $0.height < $1.width * $1.height }) else {
            throw CameraError.configuration("no photo size within \(Camera.captureLongSide) px")
        }
        output.maxPhotoDimensions = size
        device = camera
        return (camera, Self.label(size))
    }

    private static func label(_ d: CMVideoDimensions) -> String { "ProRAW \(d.width)×\(d.height)" }

    /// Starts the session, or stops it once nothing is in flight.
    func run(_ running: Bool) async {
        await withCheckedContinuation { cont in
            queue.async {
                if running {
                    self.stopWhenIdle = false
                    if !self.session.isRunning { self.session.startRunning() }
                } else if self.pending.isEmpty {
                    self.stopLocked()
                } else {
                    self.stopWhenIdle = true
                }
                cont.resume()
            }
        }
    }

    private func stopLocked() {
        stopWhenIdle = false
        if session.isRunning { session.stopRunning() }
    }

    /// One ProRAW capture, DNG only (no processed companion), flash off, oriented for the horizon.
    func capture(rotationAngle: CGFloat) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            queue.async {
                guard let format = self.output.availableRawPhotoPixelFormatTypes.first(where: AVCapturePhotoOutput.isAppleProRAWPixelFormat) else {
                    return cont.resume(throwing: CameraError.noProRAW)
                }
                let settings = AVCapturePhotoSettings(rawPixelFormatType: format)
                settings.maxPhotoDimensions = self.output.maxPhotoDimensions
                settings.photoQualityPrioritization = Camera.qualityPrioritization
                settings.flashMode = .off
                if let connection = self.output.connection(with: .video), connection.isVideoRotationAngleSupported(rotationAngle) {
                    connection.videoRotationAngle = rotationAngle
                }
                self.pending[settings.uniqueID] = cont
                self.output.capturePhoto(with: settings, delegate: self)
            }
        }
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        queue.async {
            let id = photo.resolvedSettings.uniqueID
            guard let cont = self.pending[id] else { return }
            if let error {
                self.pending[id] = nil
                return cont.resume(throwing: error)
            }
            guard photo.isRawPhoto else { return }   // a RAW-only request never delivers anything else; leave it to the final callback
            self.pending[id] = nil
            if let data = photo.fileDataRepresentation() {
                cont.resume(returning: data)
            } else {
                cont.resume(throwing: CameraError.noData)
            }
        }
    }

    /// Always the last callback for a request: a capture that delivered no photo fails here, and a deferred
    /// stop happens once nothing is in flight.
    func photoOutput(_ output: AVCapturePhotoOutput, didFinishCaptureFor resolved: AVCaptureResolvedPhotoSettings, error: Error?) {
        queue.async {
            if let cont = self.pending.removeValue(forKey: resolved.uniqueID) {
                cont.resume(throwing: error ?? CameraError.noData)
            }
            if self.pending.isEmpty, self.stopWhenIdle { self.stopLocked() }
        }
    }
}
