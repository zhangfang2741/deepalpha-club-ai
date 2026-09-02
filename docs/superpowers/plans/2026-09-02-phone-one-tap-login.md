# 运营商一键登录（本机号码自动登录/注册）

## 目标
用户点一下就用**本机手机号**完成登录或注册，无需手输号码、无需短信验证码。

## 为什么是这个方案
iOS 出于隐私限制，**App 无法直接读取 SIM 卡里的手机号**（没有任何公开 API）。
唯一合规的「自动拿到号码」途径是**运营商一键登录**：由运营商通过数据网络校验本机
号码。我们复用已在用的**阿里云号码认证服务（Dypnsapi）**，与短信验证码同一套凭据。

## 数据流
1. iOS 端阿里云 **AuthSDK** 通过**蜂窝数据网络**向运营商取一次性 `token`
   （App 全程接触不到号码明文；需要真机 + SIM + 已开启蜂窝数据）。
2. App 把 `token` POST 到后端 `POST /api/v1/auth/phone/one-tap`。
3. 后端拿 `token` 调阿里云 `GetMobile` 换回真实手机号（运营商侧已校验，可信度
   等同短信验证码）。
4. 号码归一成 E.164：**存在则登录，不存在则建号**（随机占位密码），返回本平台 JWT。

## 后端（已实现，本分支）
- `app/services/sms.py::get_mobile_by_token(token)` — 调 Dypnsapi `GetMobile`，
  只认 `GetMobileResultDTO.Mobile`；`isv.` 前缀错误 → `OneTapTokenError`（401），
  系统/鉴权错误 → `SMSSendError`（502）。
- `POST /api/v1/auth/phone/one-tap`（`app/api/v1/auth/routes.py`）— 一个入口同时
  覆盖注册和登录，限流 `chan_phone_one_tap`（默认 10 次/小时/IP）。
- 复用现有 RPC 签名、凭据（`ALIYUN_SMS_ACCESS_KEY_*`）、endpoint、region。
- 测试：`tests/services/test_sms.py::TestGetMobileOneTap`。

## iOS（网络层已就绪，SDK 待集成）
- `AuthService.oneTapLogin(token:username:)` — 已实现，直接可用。
- **待做**：集成阿里云号码认证 iOS SDK（`ATAuthSDK`）：
  1. Podfile/SPM 引入 SDK（二进制），配置 App 的一键登录方案（阿里云控制台生成的
     `secretInfo` 密钥）。
  2. `checkEnvAvailable` 预检环境（是否有 SIM/蜂窝、运营商是否支持）。
  3. `getLoginToken` 拉起运营商授权页，回调里拿到 `token`。
  4. 把 `token` 交给 `AuthService.oneTapLogin(token:)`，成功即写入 JWT 登录态。
  5. 登录/注册页加「本机号码一键登录」按钮；环境不可用时**回退**到验证码/密码登录。

## 需要在阿里云控制台完成的开通（只有账号方能做）
1. 号码认证服务开通**一键登录/本机号码校验**能力（与短信认证是同一产品下的不同能力，
   但需单独开通、单独计费）。
2. 创建**一键登录认证方案**，拿到 iOS 端 SDK 用的 `secretInfo`（绑定 Bundle ID）。
3. 三大运营商的一键登录默认覆盖移动/联通/电信；无 SIM、仅 WiFi、部分虚拟运营商
   会取不到号码，UI 必须保留验证码/密码回退。

## 成本与风控
- 每次 `GetMobile` 也按次计费，但它本身就是登录动作、且需合法运营商 token，不像短信
  可被任意目标号码轰炸，因此**不套用短信的单号每日上限**，仅按 IP 限流兜底。
