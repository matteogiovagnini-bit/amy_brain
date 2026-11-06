// Riconoscimento del testo in un'immagine con Vision (framework di sistema).
// Uso: amy-ocr /percorso/immagine.png
// Nessuna rete, nessun modello esterno: tutto avviene sul Mac.

import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write(Data("Uso: amy-ocr <immagine>\n".utf8))
    exit(2)
}

let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write(Data("Immagine non leggibile: \(path)\n".utf8))
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["it-IT", "en-US"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write(Data("OCR non riuscito: \(error.localizedDescription)\n".utf8))
    exit(4)
}

let lines = (request.results ?? []).compactMap { observation -> String? in
    observation.topCandidates(1).first?.string
}
print(lines.joined(separator: "\n"))
