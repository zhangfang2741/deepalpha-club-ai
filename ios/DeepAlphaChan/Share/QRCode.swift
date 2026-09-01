import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

/// 二维码生成。系统 CoreImage 实现，不引第三方库。
///
/// 刻意用白底黑码，不跟随 App 的深色主题上色：扫码识别率优先于视觉统一。
/// 深色底上的低对比度二维码在微信里被二次压缩后经常扫不出来。
@MainActor
enum QRCode {
    /// 同一 URL 反复生成开销白给，缓存住。key 含边长，不同尺寸各存一份。
    private static var cache: [String: UIImage] = [:]

    /// 生成二维码位图。
    ///
    /// - Parameters:
    ///   - string: 编码内容（这里是下载中转页 URL）。
    ///   - side: 目标边长（pt）。实际位图会按 `scale` 放大。
    ///   - scale: 位图倍率，默认 3（@3x）。分享图要经得起放大看。
    /// - Returns: 失败返回 nil（调用方需自行降级，不要强解包）。
    static func image(for string: String, side: CGFloat, scale: CGFloat = 3) -> UIImage? {
        let key = "\(string)@\(side)x\(scale)"
        if let cached = cache[key] { return cached }

        guard let data = string.data(using: .utf8) else { return nil }

        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        // M = 15% 容错。二维码中间没放 logo，用不着更高的 Q/H；
        // 容错越高码点越密，同样边长下反而更难扫。
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }

        // CIQRCodeGenerator 输出的是每个码点 1px 的极小图，必须放大。
        // 用整数倍最近邻放大，避免插值把码点边缘糊掉。
        let targetPixels = side * scale
        let ratio = targetPixels / output.extent.width
        let scaled = output.transformed(by: CGAffineTransform(scaleX: ratio, y: ratio))

        // 转成 CGImage 再包 UIImage：直接 UIImage(ciImage:) 在 ImageRenderer
        // 离屏渲染时可能拿不到后备位图，导出的图上二维码是空白。
        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else { return nil }

        let image = UIImage(cgImage: cgImage, scale: scale, orientation: .up)
        cache[key] = image
        return image
    }
}
