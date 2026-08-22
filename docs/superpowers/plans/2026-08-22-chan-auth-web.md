# 缠论手机号/邮箱双通道认证——Web 前端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** deepalpha.club 的登录注册支持手机号/邮箱双通道验证码注册、统一账号登录、找回密码，并增加「保持登录」勾选。

**Architecture:** 把 300 行的 `LoginRegisterForm.tsx` 拆成三个表单 + 两个共用控件 + 两个纯逻辑模块；token 读写抽出 `token-storage`，由「保持登录」决定落 `localStorage` 还是 `sessionStorage`，`client.ts` 与 zustand store 都改用它。

**Tech Stack:** Next.js 16.2.6 App Router、React 19、TypeScript、Tailwind、Zustand、Axios。

**依赖：** `docs/superpowers/plans/2026-08-22-chan-auth-backend.md` 必须先完成并合入。

**设计文档：** `docs/superpowers/specs/2026-08-22-chan-auth-phone-email-design.md`

---

## 三个前置事实

**Next 版本比训练数据新。** 按 `frontend/AGENTS.md` 的要求，动 Next API 前先查
`node_modules/next/dist/docs/`。已核对：`useRouter` 从 `next/navigation` 导入、
`router.push(href)` 在 16.2.6 下与现有代码用法一致，本计划不引入其它 Next 专有 API。

**`LoginRegisterForm.tsx` 里有 110 行的 `getErrorMessage`**（第 10–109 行），
与 `lib/api/client.ts` 的 `getApiErrorMessage` 部分重叠。但它多做了两件事：翻译
字段名（`email` → 「邮箱」）、处理后端自定义的 `data.errors` 数组。所以不是纯重复，
不能直接删掉换成 `getApiErrorMessage`——本计划把它移到独立模块给三个表单共用。

**`client.ts` 的 401 拦截器靠 URL 判断是否认证请求**（`includes('/api/v1/auth/login')`）。
新的 `/auth/login/account` 能被现有判断命中，但 `/auth/phone/register` 命不中
（它不含 `/api/v1/auth/register`）。虽然这些端点实际不返回 401，判断条件仍要收紧，
否则将来某个认证接口返回 401 会把用户莫名踢回落地页。

---

## 文件结构

**新建**

| 文件 | 职责 |
|------|------|
| `frontend/lib/auth/account.ts` | 通道类型 + 本地格式预校验（纯逻辑） |
| `frontend/lib/auth/errors.ts` | 从 LoginRegisterForm 迁出的错误消息提取 |
| `frontend/lib/auth/token-storage.ts` | token 读写，按「保持登录」选择 storage |
| `frontend/components/auth/AccountChannelTabs.tsx` | 手机号/邮箱切换 |
| `frontend/components/auth/VerificationCodeInput.tsx` | 验证码输入 + 倒计时按钮 |
| `frontend/components/auth/PasswordRules.tsx` | 密码规则清单，注册与找回密码共用 |
| `frontend/components/auth/authStyles.ts` | 三个表单共用的 Tailwind class 常量 |
| `frontend/components/auth/LoginForm.tsx` | 登录表单 |
| `frontend/components/auth/RegisterForm.tsx` | 注册表单 |
| `frontend/components/auth/ForgotPasswordForm.tsx` | 找回密码表单 |

**改造**

| 文件 | 改动 |
|------|------|
| `frontend/components/auth/LoginRegisterForm.tsx` | 缩成三个 tab 的壳 |
| `frontend/lib/api/auth.ts` | 新增九个接口函数，email 类型改可空 |
| `frontend/lib/store/auth.ts` | rememberMe + 改用 token-storage |
| `frontend/lib/api/client.ts` | 改用 token-storage，收紧 401 判断 |

---

### Task 1: 纯逻辑模块

**Files:**
- Create: `frontend/lib/auth/account.ts`
- Create: `frontend/lib/auth/token-storage.ts`

- [ ] **Step 1: 创建 account.ts**

```ts
// frontend/lib/auth/account.ts

/** 注册/登录的账号通道。 */
export type AccountChannel = 'phone' | 'email'

/**
 * 账号输入的本地预校验。
 *
 * 只做「明显不合法就别发请求」这一层，权威判断在服务端——手机号归一化规则
 * （全角转半角、去分隔符、086 前缀等）比这里复杂得多，两边各写一份必然走偏。
 * 存在的意义是省掉一次注定失败的网络往返，并在用户还没点之前就把「获取验证码」置灰。
 */

/** 中国大陆手机号：1 开头，第二位 3-9，共 11 位。与后端 utils/phone.py 的 _CN_MOBILE 一致。 */
export function isValidCNMobile(raw: string): boolean {
  const digits = raw.replace(/\D/g, '')
  return /^1[3-9]\d{9}$/.test(digits)
}

/** 邮箱格式的宽松校验，与后端 sanitize_email 的正则同源。 */
export function isValidEmail(raw: string): boolean {
  return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(raw.trim())
}

export function isValidAccount(raw: string, channel: AccountChannel): boolean {
  return channel === 'phone' ? isValidCNMobile(raw) : isValidEmail(raw)
}

/** 6 位数字验证码。 */
export function isValidCode(raw: string): boolean {
  return /^\d{6}$/.test(raw)
}

/** 密码规则，与后端 validate_password_strength 对齐：8–64 位，含大小写、数字、特殊字符。 */
export interface PasswordRuleState {
  longEnough: boolean
  hasUpper: boolean
  hasLower: boolean
  hasDigit: boolean
  hasSpecial: boolean
  allSatisfied: boolean
}

export function checkPassword(password: string): PasswordRuleState {
  const longEnough = password.length >= 8 && password.length <= 64
  const hasUpper = /[A-Z]/.test(password)
  const hasLower = /[a-z]/.test(password)
  const hasDigit = /[0-9]/.test(password)
  const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password)
  return {
    longEnough,
    hasUpper,
    hasLower,
    hasDigit,
    hasSpecial,
    allSatisfied: longEnough && hasUpper && hasLower && hasDigit && hasSpecial,
  }
}

/** +8613800138000 → 138****8000。号码属于个人信息，界面上不必完整显示。 */
export function maskPhone(e164: string): string {
  const digits = e164.startsWith('+86') ? e164.slice(3) : e164.replace(/^\+/, '')
  if (digits.length < 8) return digits
  return `${digits.slice(0, digits.length - 8)}${digits.slice(-8, -5)}****${digits.slice(-4)}`
}
```

- [ ] **Step 2: 创建 token-storage.ts**

```ts
// frontend/lib/auth/token-storage.ts

/**
 * access_token 的读写。
 *
 * 「保持登录」勾选时落 localStorage（关掉浏览器仍在），不勾选时落 sessionStorage
 * （标签页关掉就没了）。读取时两处都查，因为调用方（axios 拦截器）不知道当时
 * 用户勾没勾。
 *
 * 这个模块刻意不依赖 zustand store：client.ts 要用它，而 store 又依赖 client.ts
 * 的类型，直接引会成环。
 */

const TOKEN_KEY = 'access_token'
const REMEMBER_KEY = 'remember_me'

function canUseStorage(): boolean {
  return typeof window !== 'undefined'
}

/** 是否勾选了「保持登录」。默认 true——多数用户不希望关掉浏览器就登出。 */
export function getRememberMe(): boolean {
  if (!canUseStorage()) return true
  return localStorage.getItem(REMEMBER_KEY) !== 'false'
}

export function setRememberMe(remember: boolean): void {
  if (!canUseStorage()) return
  localStorage.setItem(REMEMBER_KEY, remember ? 'true' : 'false')
}

/** 存 token。写之前把另一处清掉，避免两处并存时读到过期的那个。 */
export function saveToken(token: string, remember: boolean): void {
  if (!canUseStorage()) return
  setRememberMe(remember)
  if (remember) {
    sessionStorage.removeItem(TOKEN_KEY)
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.setItem(TOKEN_KEY, token)
  }
}

export function loadToken(): string | null {
  if (!canUseStorage()) return null
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  if (!canUseStorage()) return
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
}
```

- [ ] **Step 3: 类型检查**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
git add frontend/lib/auth/
git commit -m "feat(web/auth): 账号校验与 token 存储的纯逻辑模块"
```

---

### Task 2: 错误消息模块迁出

**Files:**
- Create: `frontend/lib/auth/errors.ts`
- Modify: `frontend/components/auth/LoginRegisterForm.tsx`

- [ ] **Step 1: 创建 errors.ts**

把 `LoginRegisterForm.tsx` 第 9–109 行的 `getErrorMessage` 整体移过来，加上
手机号和验证码两个字段的翻译，并补一段说明它与 `getApiErrorMessage` 的分工：

```ts
// frontend/lib/auth/errors.ts

/**
 * 认证表单的错误消息提取。
 *
 * 与 lib/api/client.ts 的 getApiErrorMessage 有重叠，但多做两件事：把字段名翻成
 * 中文（email → 邮箱），以及处理后端自定义的 data.errors 数组格式。认证表单是
 * 唯一需要按字段报错的地方，所以这份留在这里，不合并进通用的那个。
 */

const FIELD_NAMES: Record<string, string> = {
  email: '邮箱',
  phone: '手机号',
  account: '账号',
  code: '验证码',
  password: '密码',
  new_password: '新密码',
  username: '用户名',
}

/** 后端返回的英文校验信息 → 中文。 */
function translateMessage(raw: string): string {
  const msg = raw.toLowerCase()
  if (msg.includes('value is not a valid email address')) return '邮箱格式不正确'
  if (msg.includes('field required') || msg.includes('missing')) return '必填'
  if (msg.includes('at least') || msg.includes('too_short')) return '长度不足'
  if (msg.includes('uppercase')) return '需包含大写字母'
  if (msg.includes('lowercase')) return '需包含小写字母'
  if (msg.includes('number')) return '需包含数字'
  if (msg.includes('special character')) return '需包含特殊字符'
  if (msg.includes('string should match pattern')) return '格式不正确'
  return raw
}

export function getAuthErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as {
      response?: { data?: Record<string, unknown>; status?: number }
    }
    const data = axiosErr.response?.data
    const status = axiosErr.response?.status

    if (data && typeof data === 'object') {
      const detail = data.detail

      // FastAPI 的 HTTPException(detail="中文提示")
      if (typeof detail === 'string') return detail

      // 本项目部分端点用 detail={"message": ..., "code": ...}
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        const obj = detail as Record<string, unknown>
        if (typeof obj.message === 'string') return obj.message
      }

      // FastAPI 参数校验错误：detail 是数组
      if (Array.isArray(detail)) {
        return detail
          .map((item: Record<string, unknown>) => {
            const loc = (item.loc as unknown[]) || []
            const field = String(loc[loc.length - 1] ?? '')
            const msg = translateMessage(String(item.msg ?? '无效值'))
            const name = FIELD_NAMES[field] || field
            return name ? `${name}: ${msg}` : msg
          })
          .join('\n')
      }

      // app/main.py 的自定义校验错误格式
      if (Array.isArray(data.errors)) {
        return (data.errors as Array<Record<string, string>>)
          .map((e) => {
            const name = FIELD_NAMES[e.field ?? ''] || e.field || ''
            const msg = translateMessage(e.message ?? '无效值')
            return name ? `${name}: ${msg}` : msg
          })
          .join('\n')
      }

      if (typeof data.message === 'string') return data.message
      if (typeof data.error === 'string') return data.error
    }

    if (status === 401) return '账号或密码错误'
    if (status === 403) return '无权访问此资源'
    if (status === 429) return '请求过于频繁，请稍后再试'
    if (status === 503) return '服务暂不可用，请稍后再试'
  }

  if (err && typeof err === 'object' && 'message' in err) {
    const msg = (err as { message: string }).message
    if (msg.toLowerCase().includes('network')) return '网络连接失败，请检查网络'
    if (msg.toLowerCase().includes('timeout')) return '请求超时，请稍后重试'
  }

  return '操作失败，请稍后重试'
}
```

注意与原实现的两处差异，都是有意的：401 的文案从「邮箱或密码错误」改成
「账号或密码错误」（现在也可能是手机号）；新增 503 的处理（验证码渠道未配置时
后端返回它，不处理的话用户只会看到「操作失败」）。

- [ ] **Step 2: 从 LoginRegisterForm.tsx 删掉旧实现**

删除该文件第 9–109 行（注释 `// 从 Axios 错误中提取后端 detail 消息` 到
`getErrorMessage` 函数结束的 `}`），并在文件顶部 import 区加：

```ts
import { getAuthErrorMessage } from '@/lib/auth/errors'
```

把文件里两处 `getErrorMessage(err)` 改为 `getAuthErrorMessage(err)`。

- [ ] **Step 3: 类型检查与构建**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`
Expected: 无报错

- [ ] **Step 4: 提交**

```bash
git add frontend/lib/auth/errors.ts frontend/components/auth/LoginRegisterForm.tsx
git commit -m "refactor(web/auth): 错误消息提取迁出为独立模块"
```

---

### Task 3: token 存储接入

**Files:**
- Modify: `frontend/lib/store/auth.ts`
- Modify: `frontend/lib/api/client.ts`

- [ ] **Step 1: 改 store**

整体替换 `frontend/lib/store/auth.ts`：

```ts
// frontend/lib/store/auth.ts
import { create } from 'zustand'
import type { AuthUser } from '@/lib/api/auth'
import {
  clearToken,
  getRememberMe,
  loadToken,
  saveToken,
  setRememberMe,
} from '@/lib/auth/token-storage'

interface AuthState {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  hydrated: boolean // hydrate() 是否已执行，用于防止 AuthGuard 在检查完成前跳转
  rememberMe: boolean

  setAuth: (token: string, user: AuthUser | null) => void
  clearAuth: () => void
  hydrate: () => void // 从 storage 恢复状态（客户端调用）
  setRemember: (remember: boolean) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  hydrated: false,
  // 默认 true，与 token-storage.getRememberMe 的默认一致
  rememberMe: true,

  setAuth: (token, user) => {
    saveToken(token, get().rememberMe)
    set({ token, user, isAuthenticated: true })
  },

  clearAuth: () => {
    clearToken()
    set({ token: null, user: null, isAuthenticated: false })
  },

  hydrate: () => {
    const token = loadToken()
    const remembered = getRememberMe()
    if (token) {
      set({ token, isAuthenticated: true, hydrated: true, rememberMe: remembered })
    } else {
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        hydrated: true,
        rememberMe: remembered,
      })
    }
  },

  setRemember: (remember) => {
    setRememberMe(remember)
    set({ rememberMe: remember })
  },
}))
```

- [ ] **Step 2: 改 client.ts 的请求拦截器**

把这一段：

```ts
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})
```

改为：

```ts
apiClient.interceptors.request.use((config) => {
  // 走 token-storage 而不是直接读 localStorage：不勾「保持登录」时 token 在
  // sessionStorage 里，只查 localStorage 会导致所有请求都不带 Authorization 头。
  const token = loadToken()
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})
```

并在文件顶部 import 区加：

```ts
import { clearToken, loadToken } from '@/lib/auth/token-storage'
```

- [ ] **Step 3: 改 client.ts 的响应拦截器**

把这一段：

```ts
      const isAuthRequest = error.config?.url?.includes('/api/v1/auth/login') || 
                           error.config?.url?.includes('/api/v1/auth/register')

      if (!isAuthRequest && typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
        window.location.href = '/'
      }
```

改为：

```ts
      // 认证类请求自己处理 401，不要自动跳转。用前缀判断而不是逐个列举路径：
      // 双通道认证下路径有 /auth/login/account、/auth/phone/register 等多种形态，
      // 漏掉一个就会让用户在表单里莫名其妙被踢回落地页。
      const url = error.config?.url ?? ''
      const isAuthRequest =
        url.includes('/api/v1/auth/login') ||
        url.includes('/api/v1/auth/register') ||
        url.includes('/api/v1/auth/phone/') ||
        url.includes('/api/v1/auth/password-reset')

      if (!isAuthRequest && typeof window !== 'undefined') {
        clearToken()
        window.location.href = '/'
      }
```

- [ ] **Step 4: 类型检查**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`
Expected: 无报错

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/store/auth.ts frontend/lib/api/client.ts
git commit -m "feat(web/auth): token 按保持登录选择 storage，收紧 401 拦截判断"
```

---

### Task 4: API 层

**Files:**
- Modify: `frontend/lib/api/auth.ts`

- [ ] **Step 1: 改 AuthUser 与响应类型**

后端 email 已改可空。把 `frontend/lib/api/auth.ts` 顶部的类型改为：

```ts
export interface AuthUser {
  id: number
  email: string | null
  phone: string | null
  username: string | null
}

// 登录响应（只含 token，无用户信息）
export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at: string
}

// 注册响应（含用户信息 + token）
export interface RegisterResponse {
  id: number
  email: string | null
  phone: string | null
  username: string | null
  token: LoginResponse
}
```

同时把文件后半段 `UserProfileResponse` 里的 `email` 也改成 `string | null`，
并补 `phone: string | null`。

- [ ] **Step 2: 替换 login / register 并新增接口**

删除现有的 `login`（form-urlencoded 打 `/auth/login`）和 `register`
（无验证码打 `/auth/register`），替换为：

```ts
import type { AccountChannel } from '@/lib/auth/account'

// 统一登录：account 可以是手机号或邮箱，由服务端判别
export const login = async (account: string, password: string): Promise<LoginResponse> => {
  const response = await apiClient.post<LoginResponse>('/api/v1/auth/login/account', {
    account,
    password,
  })
  return response.data
}

// 发码类接口的响应
export interface SentResponse {
  sent: boolean
}

export interface ResetResponse {
  reset: boolean
}

// 请求注册验证码
export const requestRegisterCode = async (
  account: string,
  channel: AccountChannel
): Promise<SentResponse> => {
  const url =
    channel === 'email'
      ? '/api/v1/auth/register/request-code'
      : '/api/v1/auth/phone/register/request-code'
  const body = channel === 'email' ? { email: account } : { phone: account }
  const response = await apiClient.post<SentResponse>(url, body)
  return response.data
}

// 校验验证码并注册
export const register = async (
  account: string,
  channel: AccountChannel,
  code: string,
  password: string,
  username?: string
): Promise<RegisterResponse> => {
  const url = channel === 'email' ? '/api/v1/auth/register/verify' : '/api/v1/auth/phone/register'
  const idField = channel === 'email' ? { email: account } : { phone: account }
  const response = await apiClient.post<RegisterResponse>(url, {
    ...idField,
    code,
    password,
    ...(username ? { username } : {}),
  })
  return response.data
}

// 请求找回密码验证码
//
// 注意：无论账号是否存在服务端都返回成功（防账号枚举），所以调用成功不代表
// 账号存在，界面上不能据此提示「账号已找到」。
export const requestPasswordResetCode = async (
  account: string,
  channel: AccountChannel
): Promise<SentResponse> => {
  const url =
    channel === 'email'
      ? '/api/v1/auth/password-reset/request'
      : '/api/v1/auth/phone/password-reset/request'
  const body = channel === 'email' ? { email: account } : { phone: account }
  const response = await apiClient.post<SentResponse>(url, body)
  return response.data
}

// 凭验证码设置新密码
export const confirmPasswordReset = async (
  account: string,
  channel: AccountChannel,
  code: string,
  newPassword: string
): Promise<ResetResponse> => {
  const url =
    channel === 'email'
      ? '/api/v1/auth/password-reset/confirm'
      : '/api/v1/auth/phone/password-reset/confirm'
  const idField = channel === 'email' ? { email: account } : { phone: account }
  const response = await apiClient.post<ResetResponse>(url, {
    ...idField,
    code,
    new_password: newPassword,
  })
  return response.data
}
```

- [ ] **Step 3: 类型检查**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`
Expected: FAIL。`LoginRegisterForm.tsx` 调 `login(email, password)` 和
`register(email, password, username)`，签名变了。Task 6 修。同时可能有别处
（如 `app/settings/page.tsx`）引用 `AuthUser.email` 时因可空报错——记下清单，
在 Task 6 一并修。

- [ ] **Step 4: 提交**

```bash
git add frontend/lib/api/auth.ts
git commit -m "feat(web/auth): API 层接入双通道注册登录与找回密码"
```

---

### Task 5: 共用控件

**Files:**
- Create: `frontend/components/auth/authStyles.ts`
- Create: `frontend/components/auth/AccountChannelTabs.tsx`
- Create: `frontend/components/auth/VerificationCodeInput.tsx`

- [ ] **Step 1: 创建 authStyles.ts**

三个表单会重复用同一套 class 串，抽成常量：

```ts
// frontend/components/auth/authStyles.ts

export const inputClass =
  'w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors'

export const labelClass =
  'block text-xs font-medium text-slate-500 mb-1.5 uppercase tracking-wide'

export const submitClass =
  'w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-1 shadow-sm shadow-blue-600/20'

export const errorBoxClass = 'bg-red-500/10 border border-red-500/30 rounded-lg p-3'
```

- [ ] **Step 2: 创建 AccountChannelTabs.tsx**

```tsx
'use client'
import type { AccountChannel } from '@/lib/auth/account'

interface Props {
  channel: AccountChannel
  onChange: (channel: AccountChannel) => void
}

/** 手机号 / 邮箱切换。 */
export default function AccountChannelTabs({ channel, onChange }: Props) {
  const tabs: Array<{ value: AccountChannel; label: string }> = [
    { value: 'phone', label: '手机号' },
    { value: 'email', label: '邮箱' },
  ]

  return (
    <div className="flex bg-slate-100 rounded-lg p-1">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-all ${
            channel === t.value
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: 创建 VerificationCodeInput.tsx**

```tsx
'use client'
import { useEffect, useRef, useState } from 'react'
import { inputClass } from './authStyles'

interface Props {
  code: string
  onCodeChange: (code: string) => void
  /** 账号格式合法才允许发码 */
  canRequest: boolean
  /** 返回 true 表示发送成功，才开始倒计时 */
  onRequest: () => Promise<boolean>
}

/**
 * 验证码输入 + 获取按钮。
 *
 * 倒计时秒数与后端 EMAIL_CODE_RESEND_COOLDOWN 对齐（60 秒）。这只是体验优化，
 * 真正的冷却由服务端把关——刷新页面绕不过去。
 */
const COOLDOWN_SECONDS = 60

export default function VerificationCodeInput({
  code,
  onCodeChange,
  canRequest,
  onRequest,
}: Props) {
  const [remaining, setRemaining] = useState(0)
  const [sending, setSending] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 组件卸载时清掉定时器，否则用户在倒计时中间切走会留下一个空转的 interval
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const startCountdown = () => {
    setRemaining(COOLDOWN_SECONDS)
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          if (timerRef.current) clearInterval(timerRef.current)
          return 0
        }
        return r - 1
      })
    }, 1000)
  }

  const handleRequest = async () => {
    setSending(true)
    try {
      const sent = await onRequest()
      if (sent) startCountdown()
    } finally {
      setSending(false)
    }
  }

  const enabled = canRequest && remaining === 0 && !sending

  return (
    <div className="flex gap-2">
      <input
        type="text"
        inputMode="numeric"
        required
        autoComplete="one-time-code"
        value={code}
        // 只留数字并截断，避免粘贴进来一串带空格的内容
        onChange={(e) => onCodeChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
        placeholder="6 位验证码"
        className={inputClass}
      />
      <button
        type="button"
        onClick={handleRequest}
        disabled={!enabled}
        className="shrink-0 px-3 py-2.5 text-xs font-medium rounded-lg border border-slate-200 text-blue-600 disabled:text-slate-400 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors whitespace-nowrap"
      >
        {sending ? '发送中…' : remaining > 0 ? `${remaining}s` : '获取验证码'}
      </button>
    </div>
  )
}
```

- [ ] **Step 4: 类型检查**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`
Expected: 仍是 Task 4 遗留的 `LoginRegisterForm.tsx` 报错，但不应出现这三个新文件自身的错误

- [ ] **Step 5: 提交**

```bash
git add frontend/components/auth/authStyles.ts frontend/components/auth/AccountChannelTabs.tsx frontend/components/auth/VerificationCodeInput.tsx
git commit -m "feat(web/auth): 认证表单共用控件与验证码倒计时输入"
```

---

### Task 6: 三个表单 + 外壳

**Files:**
- Create: `frontend/components/auth/LoginForm.tsx`
- Create: `frontend/components/auth/RegisterForm.tsx`
- Create: `frontend/components/auth/ForgotPasswordForm.tsx`
- Modify: `frontend/components/auth/LoginRegisterForm.tsx`

- [ ] **Step 1: 创建 LoginForm.tsx**

```tsx
'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/auth'
import { getAuthErrorMessage } from '@/lib/auth/errors'
import { isValidAccount, type AccountChannel } from '@/lib/auth/account'
import AccountChannelTabs from './AccountChannelTabs'
import { errorBoxClass, inputClass, labelClass, submitClass } from './authStyles'

interface Props {
  onForgotPassword: () => void
}

export default function LoginForm({ onForgotPassword }: Props) {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)
  const rememberMe = useAuthStore((s) => s.rememberMe)
  const setRemember = useAuthStore((s) => s.setRemember)

  const [channel, setChannel] = useState<AccountChannel>('phone')
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const accountValid = isValidAccount(account, channel)

  const switchChannel = (c: AccountChannel) => {
    setChannel(c)
    // 切换通道时清空账号，否则手机号会留在邮箱框里显得莫名其妙
    setAccount('')
    setError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await login(account, password)
      // 登录响应不含用户信息，user 设为 null
      setAuth(res.access_token, null)
      router.push('/dashboard')
    } catch (err) {
      setError(getAuthErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <AccountChannelTabs channel={channel} onChange={switchChannel} />

      <div>
        <label className={labelClass}>{channel === 'phone' ? '手机号' : '邮箱'}</label>
        <input
          type={channel === 'phone' ? 'tel' : 'email'}
          inputMode={channel === 'phone' ? 'numeric' : 'email'}
          required
          autoComplete={channel === 'phone' ? 'tel' : 'email'}
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          placeholder={channel === 'phone' ? '13800138000' : 'you@example.com'}
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass}>密码</label>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className={inputClass}
        />
      </div>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRemember(e.target.checked)}
            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500/40"
          />
          保持登录
        </label>
        <button
          type="button"
          onClick={onForgotPassword}
          className="text-xs text-blue-600 hover:text-blue-500"
        >
          忘记密码？
        </button>
      </div>

      {error && (
        <div className={errorBoxClass}>
          <p className="text-sm text-red-400 whitespace-pre-line">{error}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !accountValid || !password}
        className={submitClass}
      >
        {loading ? '登录中...' : '登录'}
      </button>
    </form>
  )
}
```

- [ ] **Step 2: 创建 RegisterForm.tsx**

```tsx
'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { register, requestRegisterCode } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/auth'
import { getAuthErrorMessage } from '@/lib/auth/errors'
import { checkPassword, isValidAccount, isValidCode, type AccountChannel } from '@/lib/auth/account'
import AccountChannelTabs from './AccountChannelTabs'
import VerificationCodeInput from './VerificationCodeInput'
import PasswordRules from './PasswordRules'
import { errorBoxClass, inputClass, labelClass, submitClass } from './authStyles'

export default function RegisterForm() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)

  const [channel, setChannel] = useState<AccountChannel>('phone')
  const [account, setAccount] = useState('')
  const [code, setCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const accountValid = isValidAccount(account, channel)
  const rules = checkPassword(password)
  const canSubmit = accountValid && isValidCode(code) && rules.allSatisfied

  const switchChannel = (c: AccountChannel) => {
    setChannel(c)
    // 验证码是绑在具体账号上的，切换通道后留着只会误导
    setAccount('')
    setCode('')
    setError('')
  }

  const handleRequestCode = async (): Promise<boolean> => {
    setError('')
    try {
      await requestRegisterCode(account, channel)
      return true
    } catch (err) {
      setError(getAuthErrorMessage(err))
      return false
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await register(account, channel, code, password, username || undefined)
      setAuth(res.token.access_token, {
        id: res.id,
        email: res.email,
        phone: res.phone,
        username: res.username,
      })
      router.push('/dashboard')
    } catch (err) {
      setError(getAuthErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <AccountChannelTabs channel={channel} onChange={switchChannel} />

      <div>
        <label className={labelClass}>{channel === 'phone' ? '手机号' : '邮箱'}</label>
        <input
          type={channel === 'phone' ? 'tel' : 'email'}
          inputMode={channel === 'phone' ? 'numeric' : 'email'}
          required
          autoComplete={channel === 'phone' ? 'tel' : 'email'}
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          placeholder={channel === 'phone' ? '13800138000' : 'you@example.com'}
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass}>验证码</label>
        <VerificationCodeInput
          code={code}
          onCodeChange={setCode}
          canRequest={accountValid}
          onRequest={handleRequestCode}
        />
      </div>

      <div>
        <label className={labelClass}>
          用户名 <span className="text-slate-400 normal-case tracking-normal">（可选）</span>
        </label>
        <input
          type="text"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="昵称"
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass}>密码</label>
        <input
          type="password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="至少8位，含大小写字母、数字、特殊字符"
          className={inputClass}
        />
        {password && <PasswordRules rules={rules} />}
      </div>

      {error && (
        <div className={errorBoxClass}>
          <p className="text-sm text-red-400 whitespace-pre-line">{error}</p>
        </div>
      )}

      <button type="submit" disabled={loading || !canSubmit} className={submitClass}>
        {loading ? '注册中...' : '注册'}
      </button>
    </form>
  )
}
```

- [ ] **Step 3: 创建 PasswordRules.tsx**

上一步引用了它，补上：

```tsx
'use client'
import type { PasswordRuleState } from '@/lib/auth/account'

interface Props {
  rules: PasswordRuleState
}

/** 密码规则清单。注册和找回密码两个表单共用。 */
export default function PasswordRules({ rules }: Props) {
  const items: Array<[string, boolean]> = [
    ['8–64 位长度', rules.longEnough],
    ['含大写字母', rules.hasUpper],
    ['含小写字母', rules.hasLower],
    ['含数字', rules.hasDigit],
    ['含特殊字符（如 !@#$%^&*）', rules.hasSpecial],
  ]

  return (
    <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
      {items.map(([label, ok]) => (
        <li
          key={label}
          className={`text-[11px] flex items-center gap-1 ${
            ok ? 'text-emerald-600' : 'text-slate-400'
          }`}
        >
          <span>{ok ? '✓' : '○'}</span>
          {label}
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: 创建 ForgotPasswordForm.tsx**

```tsx
'use client'
import { useState } from 'react'
import { confirmPasswordReset, requestPasswordResetCode } from '@/lib/api/auth'
import { getAuthErrorMessage } from '@/lib/auth/errors'
import { checkPassword, isValidAccount, isValidCode, type AccountChannel } from '@/lib/auth/account'
import AccountChannelTabs from './AccountChannelTabs'
import VerificationCodeInput from './VerificationCodeInput'
import PasswordRules from './PasswordRules'
import { errorBoxClass, inputClass, labelClass, submitClass } from './authStyles'

interface Props {
  /** 重置成功后回登录页 */
  onDone: () => void
}

/**
 * 找回密码。
 *
 * 服务端对未注册的账号也返回「已发送」（防账号枚举），所以这里不能因为发码成功
 * 就提示「账号已找到」——用户输错账号时会一直收不到码，这是有意为之的取舍。
 */
export default function ForgotPasswordForm({ onDone }: Props) {
  const [channel, setChannel] = useState<AccountChannel>('phone')
  const [account, setAccount] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)

  const accountValid = isValidAccount(account, channel)
  const rules = checkPassword(password)
  const canSubmit = accountValid && isValidCode(code) && rules.allSatisfied

  const switchChannel = (c: AccountChannel) => {
    setChannel(c)
    setAccount('')
    setCode('')
    setError('')
  }

  const handleRequestCode = async (): Promise<boolean> => {
    setError('')
    try {
      await requestPasswordResetCode(account, channel)
      return true
    } catch (err) {
      setError(getAuthErrorMessage(err))
      return false
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await confirmPasswordReset(account, channel, code, password)
      setDone(true)
      setTimeout(onDone, 1200)
    } catch (err) {
      setError(getAuthErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <AccountChannelTabs channel={channel} onChange={switchChannel} />

      <div>
        <label className={labelClass}>{channel === 'phone' ? '手机号' : '邮箱'}</label>
        <input
          type={channel === 'phone' ? 'tel' : 'email'}
          inputMode={channel === 'phone' ? 'numeric' : 'email'}
          required
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          placeholder={channel === 'phone' ? '13800138000' : 'you@example.com'}
          className={inputClass}
        />
      </div>

      <div>
        <label className={labelClass}>验证码</label>
        <VerificationCodeInput
          code={code}
          onCodeChange={setCode}
          canRequest={accountValid}
          onRequest={handleRequestCode}
        />
      </div>

      <div>
        <label className={labelClass}>新密码</label>
        <input
          type="password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="至少8位，含大小写字母、数字、特殊字符"
          className={inputClass}
        />
        {password && <PasswordRules rules={rules} />}
      </div>

      {error && (
        <div className={errorBoxClass}>
          <p className="text-sm text-red-400 whitespace-pre-line">{error}</p>
        </div>
      )}

      {done && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3">
          <p className="text-sm text-emerald-600">密码已重置，请用新密码登录</p>
        </div>
      )}

      <button type="submit" disabled={loading || !canSubmit || done} className={submitClass}>
        {loading ? '提交中...' : '重置密码'}
      </button>
    </form>
  )
}
```

- [ ] **Step 5: 把 LoginRegisterForm.tsx 缩成外壳**

整体替换为：

```tsx
'use client'
import { useState } from 'react'
import LoginForm from './LoginForm'
import RegisterForm from './RegisterForm'
import ForgotPasswordForm from './ForgotPasswordForm'

type Tab = 'login' | 'register' | 'forgot'

const COPY: Record<Tab, { title: string; subtitle: string }> = {
  login: { title: '欢迎回来', subtitle: '登录以访问你的投资分析面板' },
  register: { title: '创建账号', subtitle: '免费注册，开始智能投资分析' },
  forgot: { title: '找回密码', subtitle: '通过手机号或邮箱验证码重置' },
}

export default function LoginRegisterForm() {
  const [tab, setTab] = useState<Tab>('login')
  const copy = COPY[tab]

  return (
    <div className="bg-white rounded-2xl border border-blue-100 p-8 w-full shadow-xl shadow-blue-900/[0.08]">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-slate-900">{copy.title}</h2>
        <p className="text-xs text-slate-400 mt-1">{copy.subtitle}</p>
      </div>

      {/* 找回密码是从登录页进去的临时状态，不占 tab 位 */}
      {tab !== 'forgot' && (
        <div className="flex mb-6 bg-slate-100 rounded-lg p-1">
          {(['login', 'register'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                tab === t
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-600'
              }`}
            >
              {t === 'login' ? '登录' : '注册'}
            </button>
          ))}
        </div>
      )}

      {tab === 'login' && <LoginForm onForgotPassword={() => setTab('forgot')} />}
      {tab === 'register' && <RegisterForm />}
      {tab === 'forgot' && (
        <>
          <ForgotPasswordForm onDone={() => setTab('login')} />
          <button
            type="button"
            onClick={() => setTab('login')}
            className="mt-4 w-full text-xs text-slate-400 hover:text-slate-600"
          >
            返回登录
          </button>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 6: 修其它引用 AuthUser.email 的地方**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npx tsc --noEmit`

对每一处因 `email` 变成 `string | null` 而报错的地方，改成
`user.email ?? (user.phone ? maskPhone(user.phone) : '—')`，
`maskPhone` 从 `@/lib/auth/account` 导入。

反复运行直到无报错。

- [ ] **Step 7: 构建**

Run: `cd /Users/zhangfang/deepalpha-club-ai/frontend && npm run build 2>&1 | tail -20`
Expected: 构建成功

- [ ] **Step 8: 提交**

```bash
git add frontend/components/auth/ frontend/app/
git commit -m "feat(web/auth): 登录注册拆分为三个表单，支持双通道与找回密码"
```

---

### Task 7: 手工验收

**前置：** 后端跑起来（`make dev`），前端 `npm run dev`，本地 `.env` 填好 `SMTP_*`。

- [ ] **Step 1: 走一遍测试矩阵**

| # | 操作 | 预期 |
|---|------|------|
| 1 | 打开落地页 | 默认「登录」tab，通道默认「手机号」，「保持登录」已勾选 |
| 2 | 切到「邮箱」 | 账号框清空，placeholder 变成 you@example.com |
| 3 | 手机号输 `138` | 登录按钮置灰 |
| 4 | 手机号输 `13800138000` + 密码 | 登录按钮可点 |
| 5 | 错误密码登录 | 提示「账号或密码错误」 |
| 6 | 注册 tab，账号未填完 | 「获取验证码」置灰 |
| 7 | 邮箱填完整后点获取验证码 | 变 60s 倒计时且不可点 |
| 8 | 倒计时中刷新页面 | 再次点击被服务端拒（429），提示「请求过于频繁」而不是「操作失败」 |
| 9 | 收到邮件 | 署名是「DeepAlpha 缠论」 |
| 10 | 密码框输入 | 规则清单实时打勾 |
| 11 | 验证码正确 + 合规密码 | 注册成功跳 /dashboard |
| 12 | 手机通道发码（无阿里云凭据） | 提示「服务暂不可用，请稍后再试」而不是「操作失败」 |
| 13 | 勾着「保持登录」→ 关标签页重开 | 仍是登录态 |
| 14 | 取消勾选后登录 → 关标签页重开 | 回到落地页要求重新登录 |
| 15 | 取消勾选后登录，在同一标签页刷新 | 仍是登录态（sessionStorage 还在） |
| 16 | 登录后访问任意需要认证的页面 | 请求带上 Authorization 头，不被踢回落地页 |
| 17 | 忘记密码 → 走完流程 | 提示「密码已重置」，自动回登录 tab，新密码能登录 |

第 14、15、16 项是本次改动风险最集中的地方（token 换 storage），务必逐一确认。

- [ ] **Step 2: 修掉矩阵里发现的问题**

每修一个单独提交。

- [ ] **Step 3: 提交收尾**

```bash
git add -A
git commit -m "chore(web/auth): 双通道认证手工验收通过"
```

---

## 已知取舍

- **没有前端单元测试。** 项目现状没有前端测试框架，本计划不引入——加 Vitest +
  Testing Library 是独立的一件事，混进来会让这次改动的评审面失控。`lib/auth/account.ts`
  是纯函数，将来补测试时可直接覆盖。
- **只做中国大陆手机号。** 与 iOS 端一致。
- **legacy 的 `/auth/register` 不再被 Web 调用**，但服务端保留（已上架的旧版 App 在用）。
