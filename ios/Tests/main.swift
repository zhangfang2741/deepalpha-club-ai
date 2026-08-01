import Foundation

var failures = 0
func check(_ input: String, _ answer: String, _ expected: ReviewRating, _ note: String) {
    let got = DictationJudge.judge(input: input, answer: answer)
    let name = { (r: ReviewRating) in ["不认识", "模糊", "认识"][r.rawValue] }
    let ok = got == expected
    if !ok { failures += 1 }
    print("\(ok ? "PASS" : "FAIL")  写「\(input.isEmpty ? "(空)" : input)」答案「\(answer)」→ \(name(got))  期望 \(name(expected))   \(note)")
}

print("=== 完全一致 / 大小写 ===")
check("boundary", "boundary", .known, "原样")
check("Boundary", "boundary", .known, "首字母大写")
check("  boundary  ", "boundary", .known, "首尾空格")
check("BOUNDARY", "boundary", .known, "全大写")

print("\n=== 连字符复合词的三种写法 ===")
check("online-shopping", "online-shopping", .known, "原样")
check("online shopping", "online-shopping", .known, "空格代替连字符")
check("onlineshopping", "online-shopping", .known, "无分隔符")
check("Online Shopping", "online-shopping", .known, "大写+空格")

print("\n=== 小错判模糊 ===")
check("boundry", "boundary", .fuzzy, "少 1 个字母")
check("boundery", "boundary", .fuzzy, "错 1 个字母")
check("bounary", "boundary", .fuzzy, "少 1 个字母")
check("online-shoping", "online-shopping", .fuzzy, "复合词少 1 个字母")

print("\n=== 错太多判不认识 ===")
check("bandory", "boundary", .unknown, "差 3 处")
check("dog", "boundary", .unknown, "完全不同")
check("", "boundary", .unknown, "空输入")
check("   ", "boundary", .unknown, "只有空格")

print("\n=== 短词必须严格（关键边界）===")
check("at", "it", .unknown, "2 字母差 1 个：不能算模糊")
check("it", "it", .known, "2 字母写对")
check("cot", "cat", .unknown, "3 字母差 1 个：不能算模糊")
check("cat", "cat", .known, "3 字母写对")
check("hous", "house", .fuzzy, "5 字母差 1 个：可以算模糊")
check("cart", "card", .unknown, "4 字母差 1 个：不能算模糊")
check("housr", "house", .fuzzy, "5 字母差 1 个")
check("hoosr", "house", .unknown, "5 字母差 2 个：超出该长度的容忍度")
check("boundari", "boundary", .fuzzy, "8 字母差 1 个")
check("bounderi", "boundary", .fuzzy, "8 字母差 2 个")

print("\n=== 归一化本身 ===")
print(DictationJudge.normalize("  Online-Shopping ") == "onlineshopping" ? "PASS  normalize" : "FAIL  normalize")
print(DictationJudge.levenshtein(Array("kitten"), Array("sitting")) == 3 ? "PASS  levenshtein(kitten,sitting)=3" : "FAIL  levenshtein")

print("\n失败数: \(failures)")
exit(failures == 0 ? 0 : 1)
