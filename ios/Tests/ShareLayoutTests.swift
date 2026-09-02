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
        let pad = ShareLayout.outerPadding
        let gap = ShareLayout.gap

        print("=== 竖屏截图（iPhone 15 Pro，390x844）===")
        let portrait = ShareLayout.compute(screenshotSize: CGSize(width: 390, height: 844))
        expect(portrait.totalSize.width, 390 + pad * 2, "总宽 = 截图宽 + 左右留白")
        expect(portrait.totalSize.height,
               844 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight + gap * 2,
               "总高 = 截图高 + 品牌头 + 免责条 + 两处间距")
        expect(portrait.bannerRect.origin.y, 0, "品牌头在最上")
        expect(portrait.screenshotRect.origin.y, ShareLayout.bannerHeight + gap,
               "截图与品牌头之间留一个 gap")
        expect(portrait.disclaimerRect.origin.y, ShareLayout.bannerHeight + gap + 844 + gap,
               "免责条在最下，且与截图之间留一个 gap")
        expect(portrait.bannerRect.width, 390 + pad * 2, "品牌头通栏，不是写死 375")
        expect(portrait.screenshotRect.width, 390, "截图区宽度 = 原截图宽")

        print("\n=== 横屏截图（全屏图表，844x390）===")
        let landscape = ShareLayout.compute(screenshotSize: CGSize(width: 844, height: 390))
        expect(landscape.totalSize.width, 844 + pad * 2, "横图总宽 = 截图宽 + 左右留白")
        expect(landscape.bannerRect.width, 844 + pad * 2, "品牌头随横图变宽")
        expect(landscape.totalSize.height,
               390 + ShareLayout.bannerHeight + ShareLayout.disclaimerHeight + gap * 2,
               "横图总高")

        print("\n=== 截图内嵌为卡片（左右留白 + 通栏品牌条）===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expect(l.screenshotRect.minX, pad, "\(name)：截图卡片左侧留白")
            expect(l.screenshotRect.maxX, l.totalSize.width - pad, "\(name)：截图卡片右侧留白")
            expect(l.bannerRect.width, l.totalSize.width, "\(name)：品牌头通栏")
            expect(l.disclaimerRect.width, l.totalSize.width, "\(name)：免责条通栏")
            expect(l.bannerRect.minX, 0, "\(name)：品牌头从最左开始")
            expect(l.disclaimerRect.minX, 0, "\(name)：免责条从最左开始")
            expect(l.screenshotRect.minY - l.bannerRect.maxY, gap, "\(name)：品牌头与截图之间恰好一个 gap")
            expect(l.disclaimerRect.minY - l.screenshotRect.maxY, gap, "\(name)：截图与免责条之间恰好一个 gap")
        }
        expectTrue(ShareLayout.screenshotCornerRadius > 0, "截图卡片有圆角")

        print("\n=== 三块不重叠、无负高度 ===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expectTrue(l.bannerRect.maxY <= l.screenshotRect.minY + 0.01, "\(name)：品牌头不压住截图")
            expectTrue(l.screenshotRect.maxY <= l.disclaimerRect.minY + 0.01, "\(name)：截图不压住免责条")
            expectTrue(l.bannerRect.height > 0 && l.screenshotRect.height > 0 && l.disclaimerRect.height > 0,
                       "\(name)：三块高度均为正")
            expectTrue(l.disclaimerRect.maxY <= l.totalSize.height + 0.01, "\(name)：免责条不超出画布")
            expectTrue(l.screenshotRect.maxX <= l.totalSize.width + 0.01, "\(name)：截图不超出画布右边")
        }

        print("\n=== 极端宽高比 ===")
        let narrow = ShareLayout.compute(screenshotSize: CGSize(width: 100, height: 2000))
        expect(narrow.totalSize.width, 100 + pad * 2, "极窄图总宽")
        expectTrue(narrow.bannerRect.height > 0, "极窄图品牌头高度仍为正")
        let wide = ShareLayout.compute(screenshotSize: CGSize(width: 3000, height: 80))
        expect(wide.totalSize.width, 3000 + pad * 2, "极宽图总宽")
        expectTrue(wide.screenshotRect.height > 0, "极宽图截图区高度仍为正")

        print("\n\(failures == 0 ? "全部通过" : "\(failures) 项失败")")
        exit(failures == 0 ? 0 : 1)
    }
}
