// Cattura un singolo fotogramma dalla telecamera predefinita.
// Uso: amy-camera /percorso/immagine.jpg
// Tutto in locale con AVFoundation. Il primo uso richiede il permesso Telecamera.

import AVFoundation
import AppKit
import CoreImage
import Foundation

final class FrameDelegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    var data: Data?
    var imageError: Error?

    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        if self.data != nil { return }
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let image = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let jpeg = context.jpegRepresentation(of: image, colorSpace: colorSpace, options: [:]) else {
            return
        }
        self.data = jpeg
        DispatchQueue.main.async {
            CFRunLoopStop(CFRunLoopGetMain())
        }
    }

    func captureOutput(_ output: AVCaptureOutput,
                       didDrop sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
    }
}

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write(Data("Uso: amy-camera <immagine>\n".utf8))
    exit(2)
}

let path = CommandLine.arguments[1]
guard let device = AVCaptureDevice.default(for: .video) else {
    FileHandle.standardError.write(Data("Nessuna telecamera disponibile.\n".utf8))
    exit(3)
}

switch AVCaptureDevice.authorizationStatus(for: .video) {
case .authorized:
    break
case .notDetermined:
    let semaphore = DispatchSemaphore(value: 0)
    AVCaptureDevice.requestAccess(for: .video) { _ in semaphore.signal() }
    // Un binario lanciato da terminale non sempre riceve il callback del
    // permesso: non blocchiamo oltre cinque secondi e riportiamo lo stato reale.
    _ = semaphore.wait(timeout: .now() + 5)
    if AVCaptureDevice.authorizationStatus(for: .video) != .authorized {
        FileHandle.standardError.write(Data("Permesso Telecamera non concesso: avvia Amy Core e riprova.\n".utf8))
        exit(9)
    }
default:
    FileHandle.standardError.write(Data("Permesso Telecamera negato: aprilo in Impostazioni di Sistema.\n".utf8))
    exit(9)
}

do {
    let session = AVCaptureSession()
    session.sessionPreset = .photo
    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else {
        FileHandle.standardError.write(Data("Input telecamera non disponibile.\n".utf8))
        exit(4)
    }
    session.addInput(input)

    let output = AVCaptureVideoDataOutput()
    output.alwaysDiscardsLateVideoFrames = true
    guard session.canAddOutput(output) else {
        FileHandle.standardError.write(Data("Output video non disponibile.\n".utf8))
        exit(5)
    }
    session.addOutput(output)

    let delegate = FrameDelegate()
    output.setSampleBufferDelegate(delegate, queue: DispatchQueue(label: "amy.camera.frames"))
    session.startRunning()
    CFRunLoopRunInMode(.defaultMode, 8.0, false)
    session.stopRunning()

    guard let data = delegate.data else {
        FileHandle.standardError.write(Data("Nessun fotogramma ricevuto.\n".utf8))
        exit(7)
    }
    try data.write(to: URL(fileURLWithPath: path))
} catch {
    FileHandle.standardError.write(Data("Telecamera non disponibile: \(error.localizedDescription)\n".utf8))
    exit(8)
}
