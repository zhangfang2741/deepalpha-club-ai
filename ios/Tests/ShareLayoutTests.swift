import CoreGraphics
import Foundation

// Swift 规则：多文件一起用 swiftc 编译时，含顶层语句的文件必须叫 main.swift，
// 而 ios/Tests/main.swift 这个文件名已被 run-dictation-judge-tests.sh 占用，
// 不能重名冲突。用 @main 包一层，就能把断言代码放进任意文件名里。
@main
struct ShareLayoutTestsMain {
    static var failures = 0

    static func expect(_ actual: CGFloat, _ expected: CGFloat, _ note: String) {
        let ok = abs(actual - expected) < 0.01
        if !ok { failures += 1 }
        print("\(ok ? "PASS" : "FAIL")  \(note)  实际 \(actual) 期望 \(expected)")
    }

    static func expectTrue(_ cond: Bool, _ note: String) {
        if !cond { failures += 1 }
        print("\(cond ? "PASS" : "FAIL")  \(note)")
    }

    static func main() {
        print("=== 竖屏截图（iPhone 15 Pro，390x844）===")
        let portrait = ShareLayout.compute(screenshotSize: CGSize(width: 390, height: 844))
        expect(portrait.totalSize.width, 390, "总宽 = 截图宽")
        expect(portrait.totalSize.height, 844 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight,
               "总高 = 截图高 + 品牌头 + 免责条")
        expect(portrait.bannerRect.origin.y, 0, "品牌头在最上")
        expect(portrait.screenshotRect.origin.y, ShareLayout.bannerHeight, "截图紧接品牌头下方")
        expect(portrait.disclaimerRect.origin.y, ShareLayout.bannerHeight + 844, "免责条在最下")
        expect(portrait.bannerRect.width, 390, "品牌头宽度跟随截图，不是写死 375")

        print("\n=== 横屏截图（全屏图表，844x390）===")
        let landscape = ShareLayout.compute(screenshotSize: CGSize(width: 844, height: 390))
        expect(landscape.totalSize.width, 844, "横图总宽 = 截图宽")
        expect(landscape.bannerRect.width, 844, "品牌头随横图变宽")
        expect(landscape.totalSize.height, 390 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight,
               "横图总高")

        print("\n=== 三块不重叠、无负高度 ===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expectTrue(l.bannerRect.maxY <= l.screenshotRect.minY + 0.01, "\(name)：品牌头不压住截图")
            expectTrue(l.screenshotRect.maxY <= l.disclaimerRect.minY + 0.01, "\(name)：截图不压住免责条")
            expectTrue(l.bannerRect.height > 0 && l.screenshotRect.height > 0 && l.disclaimerRect.height > 0,
                       "\(name)：三块高度均为正")
            expectTrue(l.disclaimerRect.maxY <= l.totalSize.height + 0.01, "\(name)：免责条不超出画布")
        }

        print("\n=== 极端宽高比 ===")
        let narrow = ShareLayout.compute(screenshotSize: CGSize(width: 100, height: 2000))
        expect(narrow.totalSize.width, 100, "极窄图总宽")
        expectTrue(narrow.bannerRect.height > 0, "极窄图品牌头高度仍为正")
        let wide = ShareLayout.compute(screenshotSize: CGSize(width: 3000, height: 80))
        expect(wide.totalSize.width, 3000, "极宽图总宽")
        expectTrue(wide.screenshotRect.height > 0, "极宽图截图区高度仍为正")

        print("\n\(failures == 0 ? "全部通过" : "\(failures) 项失败")")
        exit(failures == 0 ? 0 : 1)
    }
}
