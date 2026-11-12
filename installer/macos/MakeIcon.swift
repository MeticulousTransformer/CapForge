import AppKit
import Foundation

let folder = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
for (name, pixels) in [("icon_16x16", 16), ("icon_16x16@2x", 32), ("icon_32x32", 32), ("icon_32x32@2x", 64), ("icon_128x128", 128), ("icon_128x128@2x", 256), ("icon_256x256", 256), ("icon_256x256@2x", 512), ("icon_512x512", 512), ("icon_512x512@2x", 1024)] {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let scale = CGFloat(pixels) / 1024
    let transform = NSAffineTransform()
    transform.scale(by: scale)
    transform.concat()
    NSColor(calibratedRed: 0.10, green: 0.12, blue: 0.13, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 66, y: 66, width: 892, height: 892), xRadius: 194, yRadius: 194).fill()
    NSColor(calibratedRed: 0.97, green: 0.95, blue: 0.90, alpha: 1).setStroke()
    let c = NSBezierPath()
    c.move(to: NSPoint(x: 471, y: 710)); c.curve(to: NSPoint(x: 240, y: 540), controlPoint1: NSPoint(x: 310, y: 810), controlPoint2: NSPoint(x: 240, y: 684))
    c.curve(to: NSPoint(x: 471, y: 376), controlPoint1: NSPoint(x: 240, y: 394), controlPoint2: NSPoint(x: 320, y: 298))
    c.lineWidth = 77; c.lineCapStyle = .round; c.stroke()
    let f = NSBezierPath()
    f.move(to: NSPoint(x: 594, y: 370)); f.line(to: NSPoint(x: 594, y: 720)); f.line(to: NSPoint(x: 788, y: 720))
    f.move(to: NSPoint(x: 594, y: 560)); f.line(to: NSPoint(x: 752, y: 560)); f.lineWidth = 77; f.lineCapStyle = .round; f.lineJoinStyle = .round; f.stroke()
    NSColor(calibratedRed: 0.65, green: 0.55, blue: 0.88, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 240, y: 232, width: 240, height: 53), xRadius: 15, yRadius: 15).fill()
    NSColor(calibratedRed: 0.39, green: 0.43, blue: 0.43, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 511, y: 232, width: 277, height: 53), xRadius: 15, yRadius: 15).fill()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent(name + ".png"))
}
