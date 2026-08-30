import Testing
@testable import DeepAlphaCore

@Suite("MarkdownBlockParser")
struct MarkdownBlockParserTests {
    @Test("标题分级")
    func headings() {
        let blocks = MarkdownBlockParser.parse("## 结论\n### 细节")
        #expect(blocks.count == 2)
        #expect(blocks[0] == .heading(level: 2, text: "结论"))
        #expect(blocks[1] == .heading(level: 3, text: "细节"))
    }

    @Test("无序列表聚合 + 有序列表聚合")
    func lists() {
        let blocks = MarkdownBlockParser.parse("- 第一项\n- 第二项\n1. 步骤一\n2. 步骤二")
        #expect(blocks.count == 2)
        guard case .bullet(let items) = blocks[0] else {
            Issue.record("应为 bullet"); return
        }
        #expect(items == ["第一项", "第二项"])
        guard case .ordered(let nums) = blocks[1] else {
            Issue.record("应为 ordered"); return
        }
        #expect(nums == ["步骤一", "步骤二"])
    }

    @Test("围栏代码块聚合（``` 围栏）")
    func codeFence() {
        let md = "说明\n```python\nprint(1)\nprint(2)\n```"
        let blocks = MarkdownBlockParser.parse(md)
        #expect(blocks.count == 2)
        #expect(blocks[0] == .paragraph("说明"))
        #expect(blocks[1] == .code("print(1)\nprint(2)"))
    }

    @Test("空行分段、多空行不产生空段")
    func paragraphs() {
        let blocks = MarkdownBlockParser.parse("第一段\n\n\n第二段")
        #expect(blocks == [.paragraph("第一段"), .paragraph("第二段")])
    }

    @Test("普通文本原样成段（inline 标记保留给 AttributedString）")
    func inlineKept() {
        let blocks = MarkdownBlockParser.parse("这是 **加粗** 与 `code`")
        #expect(blocks == [.paragraph("这是 **加粗** 与 `code`")])
    }

    @Test("表格行降级为代码块显示（等宽对齐）")
    func tableFallback() {
        let blocks = MarkdownBlockParser.parse("| a | b |\n|---|---|\n| 1 | 2 |")
        #expect(blocks.count == 1)
        guard case .code = blocks[0] else { Issue.record("应为 code"); return }
    }

    @Test("空串 → 空数组")
    func empty() {
        #expect(MarkdownBlockParser.parse("") == [])
        #expect(MarkdownBlockParser.parse("\n\n") == [])
    }

    @Test("未闭合代码块收尾也产出")
    func unclosedFence() {
        let blocks = MarkdownBlockParser.parse("```\nabc")
        #expect(blocks == [.code("abc")])
    }
}
