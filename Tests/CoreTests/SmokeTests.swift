import Testing
@testable import Core

@Test("包能被导入")
func smoke() {
    #expect(CorePlaceholder.ok)
}
