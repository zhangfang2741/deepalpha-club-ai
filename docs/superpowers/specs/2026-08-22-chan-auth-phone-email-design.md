# DeepAlpha 缠论：手机号 / 邮箱双通道注册登录

日期：2026-08-22
状态：设计已确认，待实施

## 背景与目标

缠论 App 目前只支持邮箱 + 密码注册登录，注册无任何验证环节，且没有找回密码入口。
本次改造：

1. 注册支持中国大陆手机号和邮箱两种通道，**两者都必须通过验证码验证**
2. 登录支持手机号和邮箱（同一个输入框，自动判别）
3. 登录页增加「保持登录」勾选
4. 顺带补上找回密码（邮箱 / 手机号双通道）
5. Web 前端（deepalpha.club）同步改造

### 已有的可复用基础设施

这套能力在 WordLens（鹦鹉背单词）那条线上已经建好，本次以复用为主而非重建：

| 模块 | 现状 | 本次处理 |
|------|------|----------|
| `app/utils/phone.py` | 中国手机号归一化成 E.164，无业务耦合 | 直接用，不改 |
| `app/services/sms.py` | 阿里云号码认证服务发码/校验，通用 | 直接用，不改 |
| `app/services/email.py` | SMTP 发验证码邮件，有 `render_register` / `render_password_reset` | 加 brand 参数 |
| `app/services/vocabulary/verification_code.py` | 签发/校验/冷却/防爆破，设计通用但 key 前缀写死 | 提升为共享模块 |
| `app/api/v1/vocabulary/auth.py` | 双通道注册登录完整路由 | 作为实现模板 |

## 关键前置结论

**短信落款不需要按 App 拆分。** 阿里云号码认证服务用的是赠送签名（`.env.example` 注释：
「赠送签名之一，如 恒创联众（不支持自定义签名）」），落款本来就不是 App 名，两个 App
共用同一签名不会造成品牌混淆。`ALIYUN_SMS_SCHEME_NAME` 留空走默认方案，同样可共用。

**邮件落款需要拆。** `SMTP_FROM_NAME` 默认值是「鹦鹉背单词」（`config.py:411`），
缠论用户会收到署名错误的邮件。

**本地 `.env` 里 `SMTP_*` 和 `ALIYUN_SMS_*` 一个键都没有**，`email.is_configured()`
和 `sms.is_configured()` 本地均为 False。真实凭据只在 Railway 上。开发期需要一条
不依赖真实发送的路径（见「本地开发」）。

**缠论 App 现在已经是自动登录**：`AuthViewModel.init()` 读到 Keychain 里的 token
就直接进主页，JWT 有效期 30 天，且没有关闭开关。因此「保持登录」勾选的语义是：
勾上 = 维持现状；**取消勾选 = 退出 App 后需要重新登录**。默认勾上。

## 架构

### 1. 数据模型

`app/models/user.py` 的 `User`（int 主键，保持不变）：

- 新增 `phone: str | None`，`unique=True`、`index=True`、`max_length=20`，存 E.164 格式
- `email` 由 `str`（非空唯一）改为 `str | None`（可空唯一）——手机号注册的用户没有邮箱

Postgres 的 unique 约束允许多行 NULL，迁移安全。「email 和 phone 至少有一个」由应用层
保证，不加 DB CHECK 约束（现有 Apple 登录路径也要经过这条规则，放在应用层便于给出中文报错）。

Alembic 自动生成迁移，不手写 SQL。

`DatabaseService` 新增 `get_user_by_phone`。

**email 变可空的连带影响**（容易漏，实施时必须一并改）：

- `schemas/auth.py` 的 `UserProfileResponse.email` 和 `UserResponse.email` 由 `str` 改 `str | None`，
  两者都增加 `phone: str | None`
- iOS `AuthModels.swift` 的 `UserProfile.email` 由 `String` 改 `String?`，增加 `phone: String?`
- Web `lib/api/auth.ts` 的 `AuthUser.email` / `UserProfileResponse.email` 同步改为可空
- `ProfileView.swift` 和 Web 设置页展示账号处，改为「有邮箱显示邮箱，否则显示打码手机号」

### 2. 验证码模块提升为共享

新建 `app/services/verification_code.py`：把 `services/vocabulary/verification_code.py`
整体搬过来，写死的 `_PREFIX = "vocab:vercode"` 改为 `CodeStore(prefix)` 类持有。
`Purpose`、`ResendTooSoonError`、`TooManyAttemptsError` 留在模块级。

`services/vocabulary/verification_code.py` 退化为薄转发层：

```python
_store = CodeStore("vocab:vercode")
# 同名模块函数逐个委托给 _store，并 re-export Purpose 与两个异常
```

这样 **`vocabulary/auth.py` 一行都不用改**，线上 Redis 里在途的验证码 key 前缀也不变，
WordLens 零回归风险。缠论侧用 `CodeStore("chan:vercode")`，两个 App 的验证码天然隔离。

### 3. 邮件品牌参数化

- `send_email(..., from_name: str | None = None)`，为 None 时取 `settings.SMTP_FROM_NAME`
- `render_register(code, ttl_minutes, brand)` / `render_password_reset(...)` 接受 brand 参数，
  默认值保持 `settings.SMTP_FROM_NAME` 以免影响 WordLens
- 新增配置 `CHAN_BRAND_NAME`（默认 `"DeepAlpha 缠论"`），同步 `.env.example` 和 `config.py`

### 4. 服务层：`app/services/account/`

遵守「api 层不写业务逻辑」的分层规则，新建：

- `codes.py`：持有缠论的 `CodeStore("chan:vercode")` 实例，按渠道分发发码与校验
  （邮箱走 `services/email`，手机走 `services/sms`）。封装「发失败就 discard 验证码
  并解除冷却」这类既有约定。
- `accounts.py`：账号标识判别（手机号 or 邮箱）、按 phone/email 查用户、建号。
  判别逻辑：先试 `normalize_phone()`，成功即为手机号，否则按邮箱处理。

### 5. API 路由

在 `app/api/v1/auth/routes.py` 新增，形状对齐 `vocabulary/auth.py`：

```
邮箱通道
POST /auth/register/request-code          {email}
POST /auth/register/verify                {email, code, password, username?}
POST /auth/password-reset/request         {email}
POST /auth/password-reset/confirm         {email, code, new_password}

手机通道
POST /auth/phone/register/request-code    {phone}
POST /auth/phone/register                 {phone, code, password, username?}
POST /auth/phone/password-reset/request   {phone}
POST /auth/phone/password-reset/confirm   {phone, code, new_password}

统一登录
POST /auth/login/account                  {account, password}   # 自动判别手机号/邮箱
```

现有 `POST /auth/register`（无验证码）与 Form 形态的 `POST /auth/login` **保留不下线**：
已上架的旧版 App 仍在调用它们。代码里标注 deprecated，待旧版本淘汰后再移除。

邮箱注册的新端点叫 `/auth/register/verify` 而不是 vocabulary 那样的 `/auth/register`，
正是因为后者已被上面这个 legacy 端点占用。手机通道无此冲突，沿用 `/auth/phone/register`。

新增 `Purpose` 用途沿用现有四个枚举值（`REGISTER` / `PASSWORD_RESET` /
`PHONE_REGISTER` / `PHONE_PASSWORD_RESET`），靠 `chan:` 前缀与 WordLens 隔离。

限流：在 `config.py` 的 `default_endpoints` 增加 `chan_register_request_code`、
`chan_phone_request_code`、`chan_password_reset_request`、`chan_password_reset_confirm`
四项，额度对齐 vocabulary 同类端点（发码 5/hour，校验 20/hour）。

注意：这些路由文件**不能用** `from __future__ import annotations`——slowapi 的
`@limiter.limit()` 依赖真实类型对象，`vocabulary/auth.py` 顶部已有此说明。

### 6. iOS 端

`LoginView`：
- 顶部 segmented Picker 切「手机号 / 邮箱」，键盘类型随之切换（`.phonePad` / `.emailAddress`）
- 「保持登录」勾选，默认开
- Apple 登录原样保留

`RegisterView`：
- 同样的 segmented Picker
- 账号框旁「获取验证码」按钮，60 秒倒计时（与后端 `EMAIL_CODE_RESEND_COOLDOWN` 对齐）
- 6 位数字验证码输入框
- 现有密码规则清单保留

新增 `ForgotPasswordView`：双通道，账号 + 验证码 + 新密码。

`AuthViewModel`：
- `@AppStorage("remember_me")`，默认 true
- `init()` 中若 `!rememberMe` 则先 `KeychainStore.clearToken()` 再判断登录态
- 新增 `requestCode` / `registerWithCode` / `loginByAccount` / `resetPassword`

手机号本地预校验用简单正则 `^1[3-9]\d{9}$`，真正的归一化以后端为准。

### 7. Web 前端

现有 `components/auth/LoginRegisterForm.tsx` 单文件 300 行同时承载登录和注册，
加上手机号、验证码、找回密码会膨胀到 600 行以上。拆分为：

```
components/auth/
  LoginForm.tsx            登录（账号 + 密码 + 保持登录）
  RegisterForm.tsx         注册（通道切换 + 验证码 + 密码）
  ForgotPasswordForm.tsx   找回密码
  AccountField.tsx         共用：手机号/邮箱切换输入框
  VerificationCodeField.tsx 共用：验证码输入 + 倒计时按钮
```

`lib/api/auth.ts` 增加对应函数；`lib/store/auth.ts`（40 行）增加 rememberMe。
Web 的「保持登录」控制 token 存 `localStorage`（勾选）还是 `sessionStorage`（不勾选）。
`lib/api/client.ts` 的请求拦截器目前写死从 `localStorage` 读 token，需要改成两处都查，
否则不勾选时请求会不带 Authorization 头。

这是本次工作范围内的定向改善，不做无关重构。

## 数据流

注册（以手机号为例）：

```
App/Web → POST /auth/phone/register/request-code {phone}
          → normalize_phone → CodeStore 冷却检查 → 阿里云 SendSmsVerifyCode
          → 记 cooldown + 重置错误计数 → 返回打码手机号
App/Web → POST /auth/phone/register {phone, code, password}
          → 错误次数检查 → 阿里云 CheckSmsVerifyCode
          → 通过：清计数 → 查重 → 建 User(phone=...) → 签 JWT → 返回 token
          → 失败：记一次失败，达上限则作废
```

邮箱通道相同，区别是验证码由本地 `CodeStore` 生成保管（存哈希），通过 SMTP 送达。

登录：

```
POST /auth/login/account {account, password}
  → 判别 account 是手机号还是邮箱
  → 对应的 get_user_by_phone / get_user_by_email
  → verify_password → 签 JWT
```

## 错误处理

沿用 vocabulary 已有的约定：

- `ResendTooSoonError` → 429，「请稍后再试」
- `TooManyAttemptsError` → 400，「验证错误次数过多，请重新获取验证码」
- 验证码错误 → 400，不区分「码错」和「码不存在」，避免探测账号是否存在
- 发送失败 → 调用 `discard_code` 作废并解除冷却，返回 502，不让用户被临时故障锁 60 秒
- 手机号格式错误 → `InvalidPhoneError` → 400，中文提示
- 未配置凭据（`is_configured()` 为 False）→ 503，日志记 `sms_not_configured` / `email_not_configured`

## 测试

重构兜底是重点，顺序上先补测试再动代码：

1. `tests/services/test_verification_code.py`——共享模块的冷却、防爆破、用途隔离、
   **前缀隔离**（`chan:` 和 `vocab:` 同一手机号互不干扰）
2. `tests/services/vocabulary/test_verification_code_shim.py`——转发层行为与迁移前一致，
   且 Redis key 前缀仍是 `vocab:vercode`
3. `tests/api/v1/auth/`——新端点的成功路径与各类失败路径，SMS/SMTP 用 mock
4. `tests/utils/test_phone.py` 若已存在则复用，不重复写

前端：`cd frontend && npx tsc --noEmit`。后端：`make check`。

## 本地开发

本地无 SMTP / 阿里云凭据。开发期两条路：

- 后端测试全部 mock 掉 `services/sms` 和 `services/email`
- 真机联调时在 Railway 上验证，或临时在本地 `.env` 填入凭据

不引入「开发模式下验证码固定为 000000」这类后门——一旦漏到生产就是完全绕过验证。

## 明确不做

- 不合并 `User` 与 `VocabularyUser` 两套账号体系，缠论和 WordLens 各自独立
- 不下线现有 `/auth/register` 和 `/auth/login`
- 不做国际手机号（`utils/phone.py` 保留了显式带国家码的国际号，但 UI 只做中国大陆）
- 不做短信品牌落款拆分（前面已论证不需要）
- 不做验证码登录（免密登录）——本次只做「验证码用于注册和找回密码」

## 实施顺序

1. 共享验证码模块提升 + 转发层 + 测试（纯重构，可独立验证）
2. 邮件 brand 参数化 + 配置
3. `User` 模型加 phone、email 改可空 + 迁移
4. `services/account/` + 新 API 路由 + 测试
5. iOS 端改造
6. Web 端改造

每步独立提交。
