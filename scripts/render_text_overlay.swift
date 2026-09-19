import AppKit

guard CommandLine.arguments.count == 3 else {
    fputs("用法：render_text_overlay.swift 文案 输出路径\n", stderr)
    exit(2)
}

let text = CommandLine.arguments[1]
let output = CommandLine.arguments[2]
let size = NSSize(width: 520, height: 128)
let image = NSImage(size: size)
image.lockFocus()

NSColor(calibratedWhite: 0.02, alpha: 0.86).setFill()
NSBezierPath(roundedRect: NSRect(origin: .zero, size: size), xRadius: 18, yRadius: 18).fill()

let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center
paragraph.lineBreakMode = .byWordWrapping
let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 29, weight: .bold),
    .foregroundColor: NSColor.white,
    .paragraphStyle: paragraph,
]
(text as NSString).draw(in: NSRect(x: 18, y: 18, width: 484, height: 92), withAttributes: attributes)
image.unlockFocus()

guard let data = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: data),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fputs("生成 PNG 失败\n", stderr)
    exit(1)
}
try png.write(to: URL(fileURLWithPath: output), options: .atomic)
