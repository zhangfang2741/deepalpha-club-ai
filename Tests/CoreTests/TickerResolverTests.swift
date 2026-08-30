import Testing
@testable import Core

@Test("US 市场不加后缀")
func us() {
    #expect(TickerResolver.resolve(raw: "nvda", market: .US) == "NVDA")
    #expect(TickerResolver.resolve(raw: "  aapl ", market: .US) == "AAPL")
}

@Test("US 已带后缀保留（如 BRK.B）")
func usWithDot() {
    #expect(TickerResolver.resolve(raw: "BRK.B", market: .US) == "BRK.B")
}

@Test("HK：strip 前导零再拼 .HK")
func hk() {
    #expect(TickerResolver.resolve(raw: "0700", market: .HK) == "700.HK")
    #expect(TickerResolver.resolve(raw: "03887", market: .HK) == "3887.HK")
    #expect(TickerResolver.resolve(raw: "700", market: .HK) == "700.HK")
}

@Test("HK：全零输入不产生空串")
func hkAllZeros() {
    #expect(TickerResolver.resolve(raw: "000", market: .HK) == "000.HK")
}

@Test("HK：已带 .HK 不重复拼")
func hkWithSuffix() {
    #expect(TickerResolver.resolve(raw: "0700.HK", market: .HK) == "0700.HK")
}

@Test("SH/SZ：前导零是有效位，直接拼后缀")
func aShares() {
    #expect(TickerResolver.resolve(raw: "600519", market: .SH) == "600519.SS")
    #expect(TickerResolver.resolve(raw: "000001", market: .SZ) == "000001.SZ")
    #expect(TickerResolver.resolve(raw: "002415", market: .SZ) == "002415.SZ")
}

@Test("空输入返回空（调用方禁用按钮）")
func empty() {
    #expect(TickerResolver.resolve(raw: "  ", market: .US) == "")
}

@Test("Market 元数据：label/placeholder/suffix")
func marketMeta() {
    #expect(Market.US.label == "美股")
    #expect(Market.HK.placeholder == "0700")
    #expect(Market.SH.suffix == ".SS")
    #expect(Market.allCases.count == 4)
}
