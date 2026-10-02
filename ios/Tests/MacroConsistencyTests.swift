import Foundation

/// 用 swiftc 与 MacroConsistency.swift 一起编译运行，无需启动模拟器（见 run-macro-consistency-tests.sh）。
@main
struct MacroConsistencyTests {
    static func main() {
        // 图里的情形：逐利 + 恐慌分 28
        assert(MacroConsistency.kind(label: "risk_on", score: 28) == .riskOnButFear)
        assert(MacroConsistency.kind(label: "risk_off", score: 70) == .riskOffButGreed)
        // 方向一致或中性：不提示
        assert(MacroConsistency.kind(label: "risk_on", score: 70) == nil)
        assert(MacroConsistency.kind(label: "risk_off", score: 28) == nil)
        assert(MacroConsistency.kind(label: "neutral", score: 10) == nil)
        assert(MacroConsistency.kind(label: "neutral", score: 90) == nil)
        // 边界：恰为 45 / 55 不算背离
        assert(MacroConsistency.kind(label: "risk_on", score: 45) == nil)
        assert(MacroConsistency.kind(label: "risk_off", score: 55) == nil)
        assert(MacroConsistency.kind(label: "risk_on", score: 44.9) == .riskOnButFear)
        assert(MacroConsistency.kind(label: "risk_off", score: 55.1) == .riskOffButGreed)
        // 未知标签
        assert(MacroConsistency.kind(label: "", score: 10) == nil)
        print("MacroConsistencyTests: all passed")
    }
}
