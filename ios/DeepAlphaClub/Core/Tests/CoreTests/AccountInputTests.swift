import Testing
@testable import DeepAlphaCore

@Suite("AccountInput")
struct AccountInputTests {
    @Test("中国大陆手机号：1 开头 + 第二位 3-9 + 共 11 位")
    func cnMobile() {
        #expect(AccountInput.isValidCNMobile("13800138000"))
        #expect(AccountInput.isValidCNMobile("19912345678"))
        // 带分隔符也认（只看数字）
        #expect(AccountInput.isValidCNMobile("138 0013 8000"))
        #expect(!AccountInput.isValidCNMobile("12800138000"))   // 第二位是 2
        #expect(!AccountInput.isValidCNMobile("1380013800"))    // 10 位
        #expect(!AccountInput.isValidCNMobile("138001380000"))  // 12 位
        #expect(!AccountInput.isValidCNMobile(""))
    }

    @Test("邮箱格式")
    func email() {
        #expect(AccountInput.isValidEmail("a@b.co"))
        #expect(AccountInput.isValidEmail(" ios-app@deepalpha.club "))  // 前后空格容忍
        #expect(!AccountInput.isValidEmail("a@b"))       // 无顶级域
        #expect(!AccountInput.isValidEmail("@b.co"))
        #expect(!AccountInput.isValidEmail("a b@c.co"))
        #expect(!AccountInput.isValidEmail(""))
    }

    @Test("按通道分派校验")
    func byChannel() {
        #expect(AccountInput.isValid("13800138000", channel: .phone))
        #expect(!AccountInput.isValid("a@b.co", channel: .phone))
        #expect(AccountInput.isValid("a@b.co", channel: .email))
        #expect(!AccountInput.isValid("13800138000", channel: .email))
    }

    @Test("6 位数字验证码")
    func code() {
        #expect(AccountInput.isValidCode("123456"))
        #expect(!AccountInput.isValidCode("12345"))
        #expect(!AccountInput.isValidCode("1234567"))
        #expect(!AccountInput.isValidCode("12345a"))
    }

    @Test("AccountChannel 元数据")
    func channelMeta() {
        #expect(AccountChannel.allCases.count == 2)
        #expect(AccountChannel.phone.title == "手机号")
        #expect(AccountChannel.email.icon == "envelope")
    }
}

@Suite("PasswordRules")
struct PasswordRulesTests {
    /// 规则必须与后端 validate_password_strength 一字不差：
    /// 前端更严会卡住后端本可接受的密码，更松则是白跑一趟网络。
    @Test("8–64 位 + 含字母 + 含数字")
    func rules() {
        let ok = PasswordRules(password: "secret88")
        #expect(ok.longEnough)
        #expect(ok.hasLetter)
        #expect(ok.hasDigit)
        #expect(ok.allSatisfied)

        #expect(!PasswordRules(password: "secre8").longEnough)      // 6 位
        #expect(!PasswordRules(password: "12345678").hasLetter)     // 纯数字
        #expect(!PasswordRules(password: "abcdefgh").hasDigit)      // 纯字母
        #expect(!PasswordRules(password: String(repeating: "a1", count: 33)).longEnough) // 66 位
    }

    @Test("边界：正好 8 位与正好 64 位都合法")
    func boundaries() {
        #expect(PasswordRules(password: "abcdefg1").allSatisfied)                       // 8
        #expect(PasswordRules(password: String(repeating: "a1", count: 32)).allSatisfied) // 64
    }
}
