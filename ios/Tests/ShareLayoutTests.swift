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
               pad + 844 + gap + ShareLayout.footerHeight + ShareLayout.disclaimerHeight + pad,
               "总高 = 上下留白 + 截图高 + 间距 + 品牌脚 + 免责条")
        expect(portrait.screenshotRect.origin.y, pad, "截图在最上，顶部有外围留白")
        expect(portrait.footerRect.origin.y, pad + 844 + gap,
               "品牌脚紧接截图下方，只隔一个收窄的 gap")
        expect(portrait.disclaimerRect.origin.y, portrait.footerRect.maxY,
               "免责条紧贴品牌脚底部，中间不再塞间距")
        expect(portrait.footerRect.width, 390, "品牌脚与截图等宽，不是通栏、也不是写死 375")
        expect(portrait.screenshotRect.width, 390, "截图区宽度 = 原截图宽")

        print("\n=== 横屏截图（全屏图表，844x390）===")
        let landscape = ShareLayout.compute(screenshotSize: CGSize(width: 844, height: 390))
        expect(landscape.totalSize.width, 844 + pad * 2, "横图总宽 = 截图宽 + 左右留白")
        expect(landscape.footerRect.width, 844, "品牌脚随横图变宽，仍与截图等宽")
        expect(landscape.totalSize.height,
               pad + 390 + gap + ShareLayout.footerHeight + ShareLayout.disclaimerHeight + pad,
               "横图总高")

        print("\n=== 截图与品牌区是两张等宽卡片，四周留白一致 ===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expect(l.screenshotRect.minX, pad, "\(name)：截图卡片左侧留白")
            expect(l.screenshotRect.maxX, l.totalSize.width - pad, "\(name)：截图卡片右侧留白")
            expect(l.screenshotRect.minY, pad, "\(name)：截图卡片顶部留白")
            // 宽度错位是用户能一眼看出的成图缺陷，这里逐条钉死左右边缘对齐
            expect(l.footerRect.width, l.screenshotRect.width, "\(name)：品牌脚与截图等宽")
            expect(l.disclaimerRect.width, l.screenshotRect.width, "\(name)：免责条与截图等宽")
            expect(l.footerRect.minX, l.screenshotRect.minX, "\(name)：品牌脚与截图左对齐")
            expect(l.disclaimerRect.minX, l.screenshotRect.minX, "\(name)：免责条与截图左对齐")
            expect(l.footerRect.maxX, l.screenshotRect.maxX, "\(name)：品牌脚与截图右对齐")
            expect(l.disclaimerRect.maxX, l.screenshotRect.maxX, "\(name)：免责条与截图右对齐")
            expect(l.totalSize.height - l.disclaimerRect.maxY, pad, "\(name)：底部留白与顶部一致")
            expect(l.footerRect.minY - l.screenshotRect.maxY, gap,
                   "\(name)：品牌脚与截图之间恰好一个 gap")
            expect(l.disclaimerRect.minY - l.footerRect.maxY, 0,
                   "\(name)：免责条紧贴品牌脚，无间距")
        }
        expectTrue(ShareLayout.screenshotCornerRadius > 0, "截图卡片有圆角")

        print("\n=== 三块不重叠、无负高度 ===")
        for (name, l) in [("竖图", portrait), ("横图", landscape)] {
            expectTrue(l.screenshotRect.maxY <= l.footerRect.minY + 0.01, "\(name)：截图不压住品牌脚")
            expectTrue(l.footerRect.maxY <= l.disclaimerRect.minY + 0.01, "\(name)：品牌脚不压住免责条")
            expectTrue(l.footerRect.height > 0 && l.screenshotRect.height > 0 && l.disclaimerRect.height > 0,
                       "\(name)：三块高度均为正")
            expectTrue(l.disclaimerRect.maxY <= l.totalSize.height + 0.01, "\(name)：免责条不超出画布")
            expectTrue(l.screenshotRect.maxX <= l.totalSize.width + 0.01, "\(name)：截图不超出画布右边")
        }

        print("\n=== 极端宽高比 ===")
        let narrow = ShareLayout.compute(screenshotSize: CGSize(width: 100, height: 2000))
        expect(narrow.totalSize.width, 100 + pad * 2, "极窄图总宽")
        expectTrue(narrow.footerRect.height > 0, "极窄图品牌脚高度仍为正")
        let wide = ShareLayout.compute(screenshotSize: CGSize(width: 3000, height: 80))
        expect(wide.totalSize.width, 3000 + pad * 2, "极宽图总宽")
        expectTrue(wide.screenshotRect.height > 0, "极宽图截图区高度仍为正")

        print("\n\(failures == 0 ? "全部通过" : "\(failures) 项失败")")
        exit(failures == 0 ? 0 : 1)
    }
}
