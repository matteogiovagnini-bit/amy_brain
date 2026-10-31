// Generatore dell'icona di Amy Core.
//
// Disegna il motivo «nucleo ad anelli» direttamente con CoreGraphics (nessuna
// libreria esterna, nessuna risorsa remota) e produce il set PNG per `iconutil`.
//
// Uso: swiftc -O make_icon.swift -o make_icon && ./make_icon <cartella-iconset>

import AppKit
import Foundation

func rgba(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: r, green: g, blue: b, alpha: a)
}

let canvas = CGFloat(1024)

func render(pixels: Int) -> Data? {
    let scale = CGFloat(pixels) / canvas
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pixels,
        pixelsHigh: pixels,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else { return nil }

    NSGraphicsContext.saveGraphicsState()
    guard let context = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
    NSGraphicsContext.current = context
    let ctx = context.cgContext
    ctx.scaleBy(x: scale, y: scale)

    // --- corpo dell'icona: quadrato arrotondato con margine
    let inset = canvas * 0.08
    let body = CGRect(x: inset, y: inset, width: canvas - inset * 2, height: canvas - inset * 2)
    let radius = body.width * 0.22
    let shape = NSBezierPath(roundedRect: body, xRadius: radius, yRadius: radius)
    shape.addClip()

    // --- sfondo notte con bagliore centrale
    let space = CGColorSpaceCreateDeviceRGB()
    if let gradient = CGGradient(
        colorsSpace: space,
        colors: [
            rgba(0.035, 0.075, 0.145, 1),
            rgba(0.012, 0.026, 0.055, 1),
        ] as CFArray,
        locations: [0, 1]
    ) {
        ctx.drawRadialGradient(
            gradient,
            startCenter: CGPoint(x: canvas / 2, y: canvas * 0.58),
            startRadius: 0,
            endCenter: CGPoint(x: canvas / 2, y: canvas * 0.58),
            endRadius: canvas * 0.72,
            options: [.drawsAfterEndLocation]
        )
    }

    let center = CGPoint(x: canvas / 2, y: canvas / 2)

    // --- alone degli anelli
    for (radius, alpha) in [(0.385, 0.10), (0.285, 0.09), (0.185, 0.08)] {
        ctx.setLineWidth(canvas * 0.055)
        ctx.setStrokeColor(rgba(0.25, 0.48, 1.0, alpha))
        ctx.strokeEllipse(in: CGRect(
            x: center.x - canvas * radius,
            y: center.y - canvas * radius,
            width: canvas * radius * 2,
            height: canvas * radius * 2
        ))
    }

    // --- anelli principali
    ctx.setLineCap(.round)
    let rings: [(CGFloat, CGColor, CGFloat)] = [
        (0.385, rgba(0.247, 0.89, 1.0, 0.95), 0.018),
        (0.285, rgba(0.149, 0.78, 1.0, 0.80), 0.014),
        (0.185, rgba(0.247, 0.89, 1.0, 0.55), 0.010),
    ]
    for (radius, color, width) in rings {
        ctx.setLineWidth(canvas * width)
        ctx.setStrokeColor(color)
        ctx.strokeEllipse(in: CGRect(
            x: center.x - canvas * radius,
            y: center.y - canvas * radius,
            width: canvas * radius * 2,
            height: canvas * radius * 2
        ))
    }

    // --- archi in blu elettrico
    ctx.setLineWidth(canvas * 0.030)
    ctx.setStrokeColor(rgba(0.184, 0.482, 1.0, 0.95))
    ctx.addArc(center: center, radius: canvas * 0.335, startAngle: 0.35, endAngle: 1.95, clockwise: false)
    ctx.strokePath()
    ctx.setStrokeColor(rgba(0.247, 0.89, 1.0, 0.85))
    ctx.addArc(center: center, radius: canvas * 0.235, startAngle: 3.35, endAngle: 4.85, clockwise: false)
    ctx.strokePath()

    // --- nucleo luminoso
    if let glow = CGGradient(
        colorsSpace: space,
        colors: [rgba(0.247, 0.89, 1.0, 0.55), rgba(0.247, 0.89, 1.0, 0)] as CFArray,
        locations: [0, 1]
    ) {
        ctx.drawRadialGradient(
            glow,
            startCenter: center,
            startRadius: 0,
            endCenter: center,
            endRadius: canvas * 0.16,
            options: []
        )
    }
    ctx.setFillColor(rgba(0.85, 0.98, 1.0, 1))
    ctx.fillEllipse(in: CGRect(
        x: center.x - canvas * 0.045,
        y: center.y - canvas * 0.045,
        width: canvas * 0.09,
        height: canvas * 0.09
    ))

    // --- particelle
    let particles: [(CGFloat, CGFloat, CGFloat, CGColor)] = [
        (0.30, 0.52, 0.020, rgba(0.247, 0.89, 1.0, 0.90)),
        (-0.34, -0.18, 0.014, rgba(0.184, 0.482, 1.0, 0.85)),
        (0.16, -0.40, 0.011, rgba(0.247, 0.89, 1.0, 0.60)),
        (-0.18, 0.44, 0.009, rgba(0.85, 0.98, 1.0, 0.70)),
    ]
    for (dx, dy, size, color) in particles {
        ctx.setFillColor(color)
        ctx.fillEllipse(in: CGRect(
            x: center.x + canvas * dx - canvas * size / 2,
            y: center.y + canvas * dy - canvas * size / 2,
            width: canvas * size,
            height: canvas * size
        ))
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])
}

guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write(Data("Uso: make_icon <cartella>\n".utf8))
    exit(2)
}

let output = CommandLine.arguments[1]
try? FileManager.default.createDirectory(atPath: output, withIntermediateDirectories: true)

let files: [(String, Int)] = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

for (name, pixels) in files {
    guard let data = render(pixels: pixels) else {
        FileHandle.standardError.write(Data("Rendering fallito per \(name)\n".utf8))
        exit(1)
    }
    try data.write(to: URL(fileURLWithPath: output).appendingPathComponent(name))
}

print("Icone generate in \(output)")
