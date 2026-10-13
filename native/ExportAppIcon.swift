import AppKit

// Export a full-bleed 1024 px background. On macOS 26, IconServices applies
// its own rounded mask; transparent padding makes it add a gray backing tile.
// Keep the approved artwork and extend only the outer background for masking.
let source = NSImage(contentsOfFile: CommandLine.arguments[1])!
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSGraphicsContext.current?.imageInterpolation = .high
NSColor(calibratedRed: 0.04, green: 0.72, blue: 0.15, alpha: 1).setFill()
NSRect(x: 0, y: 0, width: 1024, height: 1024).fill()
// Remove the source image's transparent perimeter, without cropping the mark.
source.draw(in: NSRect(x: -32, y: -32, width: 1088, height: 1088), from: .zero, operation: .sourceOver, fraction: 1)
NSGraphicsContext.restoreGraphicsState()
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
