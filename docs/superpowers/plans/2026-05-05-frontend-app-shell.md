# DeepAlpha 前端 App 框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 DeepAlpha 前端 App 整体框架——落地页（Hero + 嵌入登录/注册表单）、认证流程（真实对接后端 API）、顶部导航、四个受保护页面骨架（仪表盘/ETF/对话/设置）。

**Architecture:** Route Groups 方案：`app/(public)/page.tsx` 放落地页，`app/(dashboard)/` 放受保护页面，`(dashboard)/layout.tsx` 内含 `AuthGuard`（客户端登录态守卫）和 `TopNav`。Zustand store 只管理认证状态（state + setter，不含 API 调用），`LoginRegisterForm` 组件负责调用 API 并更新 store。JWT 存入 `localStorage`（key：`access_token`）。

**Tech Stack:** Next.js 16 App Router + TypeScript + Tailwind CSS v4 + Zustand 5 + Axios

---

## 文件清单

| 操作 | 路径 | 说明 |
|---|---|---|
| 创建 | `frontend/.env.local` | 环境变量 |
| 修改 | `frontend/lib/api/auth.ts` | 修复字段名、类型、移除不存在的端点 |
| 修改 | `frontend/lib/store/auth.ts` | 重写为 state+setter 模式，加 `hydrated` 标志 |
| 修改 | `frontend/lib/api/client.ts` | 修复 401 重定向从 `/login` 到 `/` |
| 修改 | `frontend/app/layout.tsx` | 更新 metadata（标题/描述/语言） |
| 删除 | `frontend/app/page.tsx` | 替换为 route group 结构 |
| 创建 | `frontend/app/(public)/page.tsx` | 落地页（Hero + 登录/注册表单） |
| 创建 | `frontend/app/(dashboard)/layout.tsx` | AuthGuard + TopNav 包装 |
| 创建 | `frontend/app/(dashboard)/dashboard/page.tsx` | 仪表盘骨架 |
| 创建 | `frontend/app/(dashboard)/etf/page.tsx` | ETF 资金流骨架 |
| 创建 | `frontend/app/(dashboard)/chat/page.tsx` | AI 对话骨架 |
| 创建 | `frontend/app/(dashboard)/settings/page.tsx` | 个人设置骨架 |
| 创建 | `frontend/components/auth/AuthGuard.tsx` | 客户端登录态守卫 |
| 创建 | `frontend/components/auth/LoginRegisterForm.tsx` | 登录/注册 Tab 表单 |
| 创建 | `frontend/components/layout/TopNav.tsx` | 顶部导航 |

---

## 后端 API 说明（实施前必读）

**登录** `POST /api/v1/auth/login`
- 请求：`application/x-www-form-urlencoded`，字段：`email`、`password`、`grant_type=password`
- 响应：`{ access_token: string, token_type: "bearer", expires_at: string }`
- 注意：**不返回用户信息**，登录后 store 中 `user` 为 `null`

**注册** `POST /api/v1/auth/register`
- 请求：`application/json`，字段：`email`、`password`、`username?`
- 响应：`{ id: number, email: string, username: string|null, token: { access_token: string, token_type: string, expires_at: string } }`
- 注册即登录，直接调 `setAuth()`

**不存在的端点**（现有代码有误，需修复）：`/api/v1/auth/logout`、`/api/v1/auth/me`

**密码要求**：最少 8 位，含大写字母、小写字母、数字、特殊字符（`!@#$%^&*(),.?":{}|<>`）

---

## Task 1: 配置环境变量

**Files:**
- 创建: `frontend/.env.local`

- [ ] **Step 1: 创建 .env.local**

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: 验证 .env.local 不会被提交**

检查 `frontend/.gitignore` 是否包含 `.env.local`（Next.js 默认已包含，确认即可）。

```bash
grep ".env.local" /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/.gitignore
```

预期输出：包含 `.env.local` 的行。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/.env.local  # 注意：若 .gitignore 正确配置则不会被 add
# .env.local 不需要提交，此 task 无 commit
```

---

## Task 2: 修复认证 API（lib/api/auth.ts）

**Files:**
- 修改: `frontend/lib/api/auth.ts`

现有代码有三个 Bug：
1. login 表单用了 `username` 字段，后端实际要求 `email`
2. 包含不存在的 `/logout` 和 `/me` 端点
3. 类型定义不匹配后端实际响应

- [ ] **Step 1: 完整替换 lib/api/auth.ts**

```typescript
// frontend/lib/api/auth.ts
import apiClient from './client'

export interface AuthUser {
  id: number
  email: string
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
  email: string
  username: string | null
  token: {
    access_token: string
    token_type: string
    expires_at: string
  }
}

// 登录：使用 form-urlencoded，字段名为 email（不是 username）
export const login = async (email: string, password: string): Promise<LoginResponse> => {
  const form = new URLSearchParams()
  form.append('email', email)
  form.append('password', password)
  form.append('grant_type', 'password')

  const response = await apiClient.post<LoginResponse>('/api/v1/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return response.data
}

// 注册：使用 JSON，username 可选
export const register = async (
  email: string,
  password: string,
  username?: string
): Promise<RegisterResponse> => {
  const response = await apiClient.post<RegisterResponse>('/api/v1/auth/register', {
    email,
    password,
    ...(username ? { username } : {}),
  })
  return response.data
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误（或仅有来自 store/auth.ts 的错误，因为 store 还未更新）。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/lib/api/auth.ts
git commit -m "fix: 修复认证 API——login 字段名、类型定义、移除不存在端点"
```

---

## Task 3: 重写 Zustand 认证 Store（lib/store/auth.ts）

**Files:**
- 修改: `frontend/lib/store/auth.ts`

现有 store 调用了不存在的 `getMe()` 和 `apiLogout()`。重写为 state+setter 模式，将 API 调用移到组件层。

- [ ] **Step 1: 完整替换 lib/store/auth.ts**

```typescript
// frontend/lib/store/auth.ts
import { create } from 'zustand'
import type { AuthUser } from '@/lib/api/auth'

interface AuthState {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  hydrated: boolean  // hydrate() 是否已执行，用于防止 AuthGuard 在检查完成前跳转

  setAuth: (token: string, user: AuthUser | null) => void
  clearAuth: () => void
  hydrate: () => void  // 从 localStorage 恢复状态（客户端调用）
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  hydrated: false,

  setAuth: (token, user) => {
    localStorage.setItem('access_token', token)
    set({ token, user, isAuthenticated: true })
  },

  clearAuth: () => {
    localStorage.removeItem('access_token')
    set({ token: null, user: null, isAuthenticated: false })
  },

  hydrate: () => {
    const token = localStorage.getItem('access_token')
    if (token) {
      set({ token, isAuthenticated: true, hydrated: true })
    } else {
      set({ token: null, user: null, isAuthenticated: false, hydrated: true })
    }
  },
}))
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误（与 auth.ts 的引用已解耦）。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/lib/store/auth.ts
git commit -m "refactor: 重写 auth store 为 state+setter 模式，加 hydrated 标志"
```

---

## Task 4: 修复 Axios 客户端 401 处理（lib/api/client.ts）

**Files:**
- 修改: `frontend/lib/api/client.ts`

401 时重定向到 `/login`（不存在），改为 `/`。注意：此处不能导入 store（会造成循环依赖），直接操作 localStorage 即可。

- [ ] **Step 1: 修改 401 重定向路径**

将文件中：
```typescript
window.location.href = '/login'
```
改为：
```typescript
window.location.href = '/'
```

完整替换后文件内容：

```typescript
// frontend/lib/api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// 请求拦截器：自动带上 Authorization: Bearer token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

// 响应拦截器：401 清除 token 并跳转落地页
// 注意：不能在此导入 store（循环依赖），直接操作 localStorage
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/lib/api/client.ts
git commit -m "fix: 401 重定向从 /login 改为 /"
```

---

## Task 5: 更新根布局 metadata（app/layout.tsx）

**Files:**
- 修改: `frontend/app/layout.tsx`

- [ ] **Step 1: 更新 metadata 和语言**

```typescript
// frontend/app/layout.tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DeepAlpha - AI 驱动的投资决策平台",
  description: "智能分析 ETF 资金流向，AI Agent 实时解读市场动态",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/app/layout.tsx
git commit -m "chore: 更新页面 metadata 和语言为中文"
```

---

## Task 6: 创建 AuthGuard 组件

**Files:**
- 创建: `frontend/components/auth/AuthGuard.tsx`

- [ ] **Step 1: 创建目录并写入组件**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/components/auth
```

```typescript
// frontend/components/auth/AuthGuard.tsx
'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'

interface AuthGuardProps {
  children: React.ReactNode
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter()
  const { isAuthenticated, hydrated, hydrate } = useAuthStore()

  // 挂载时从 localStorage 恢复登录状态
  useEffect(() => {
    hydrate()
  }, [hydrate])

  // hydrate 完成后，若未登录则跳转落地页
  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      router.replace('/')
    }
  }, [hydrated, isAuthenticated, router])

  // hydrate 执行中：显示加载占位（避免未登录内容闪烁）
  if (!hydrated) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
      </div>
    )
  }

  // hydrate 完成但未登录：显示空内容（useEffect 正在执行跳转）
  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/components/auth/AuthGuard.tsx
git commit -m "feat: 添加 AuthGuard 组件（客户端登录态守卫）"
```

---

## Task 7: 创建 TopNav 组件

**Files:**
- 创建: `frontend/components/layout/TopNav.tsx`

- [ ] **Step 1: 创建目录并写入组件**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/components/layout
```

```typescript
// frontend/components/layout/TopNav.tsx
'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/store/auth'

const NAV_ITEMS = [
  { href: '/dashboard', label: '仪表盘' },
  { href: '/etf', label: 'ETF 资金流' },
  { href: '/chat', label: 'AI 对话' },
  { href: '/settings', label: '设置' },
] as const

export default function TopNav() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, clearAuth } = useAuthStore()

  const handleLogout = () => {
    clearAuth()
    router.push('/')
  }

  const displayName = user?.username ?? user?.email ?? '账户'

  return (
    <nav className="h-14 border-b border-gray-200 bg-white px-6 flex items-center gap-6 flex-shrink-0">
      <Link
        href="/dashboard"
        className="font-bold text-gray-900 text-base flex-shrink-0 hover:text-gray-700 transition-colors"
      >
        DeepAlpha
      </Link>

      <div className="flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              {item.label}
            </Link>
          )
        })}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-sm text-gray-500">{displayName}</span>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-md hover:bg-gray-50 transition-colors"
        >
          退出
        </button>
      </div>
    </nav>
  )
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/components/layout/TopNav.tsx
git commit -m "feat: 添加 TopNav 组件（路由高亮 + 退出登录）"
```

---

## Task 8: 创建 (dashboard) 布局

**Files:**
- 创建: `frontend/app/(dashboard)/layout.tsx`

- [ ] **Step 1: 创建目录和布局文件**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(dashboard\)
```

```typescript
// frontend/app/(dashboard)/layout.tsx
import AuthGuard from '@/components/auth/AuthGuard'
import TopNav from '@/components/layout/TopNav'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <TopNav />
        <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8">
          {children}
        </main>
      </div>
    </AuthGuard>
  )
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add "frontend/app/(dashboard)/layout.tsx"
git commit -m "feat: 创建 dashboard route group 布局（AuthGuard + TopNav）"
```

---

## Task 9: 创建四个页面骨架

**Files:**
- 创建: `frontend/app/(dashboard)/dashboard/page.tsx`
- 创建: `frontend/app/(dashboard)/etf/page.tsx`
- 创建: `frontend/app/(dashboard)/chat/page.tsx`
- 创建: `frontend/app/(dashboard)/settings/page.tsx`

- [ ] **Step 1: 创建仪表盘页面**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(dashboard\)/dashboard
```

```typescript
// frontend/app/(dashboard)/dashboard/page.tsx
export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">仪表盘</h1>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {(['总资产', '今日收益', '持仓数量'] as const).map((label) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-sm text-gray-500 mb-3">{label}</p>
            <div className="h-7 bg-gray-100 rounded-md animate-pulse" />
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <p className="text-sm font-medium text-gray-700 mb-4">市场概览</p>
        <div className="h-48 bg-gray-50 rounded-lg flex items-center justify-center">
          <p className="text-sm text-gray-400">图表数据即将上线</p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 ETF 页面**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(dashboard\)/etf
```

```typescript
// frontend/app/(dashboard)/etf/page.tsx
export default function ETFPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">ETF 资金流</h1>

      <div className="bg-white rounded-xl border border-gray-200 p-12 flex flex-col items-center justify-center text-center">
        <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
        <h2 className="text-base font-semibold text-gray-900 mb-2">ETF 资金流数据</h2>
        <p className="text-sm text-gray-500">功能即将上线，敬请期待</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 AI 对话页面**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(dashboard\)/chat
```

```typescript
// frontend/app/(dashboard)/chat/page.tsx
export default function ChatPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">AI 对话</h1>

      {/* 消息区 */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 flex items-center justify-center mb-4">
        <div className="text-center">
          <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <p className="text-sm text-gray-500">开始与 AI 对话，分析市场动态</p>
        </div>
      </div>

      {/* 输入区（UI 骨架，暂不接 API） */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 flex gap-3 flex-shrink-0">
        <input
          type="text"
          placeholder="输入你的问题..."
          disabled
          className="flex-1 text-sm text-gray-700 outline-none bg-transparent placeholder:text-gray-400 disabled:cursor-not-allowed"
        />
        <button
          disabled
          className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg disabled:opacity-40 transition-colors"
        >
          发送
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 创建设置页面**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(dashboard\)/settings
```

```typescript
// frontend/app/(dashboard)/settings/page.tsx
export default function SettingsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">个人设置</h1>

      <div className="max-w-xl space-y-6">
        {/* 账户信息 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">账户信息</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
              <input
                type="email"
                disabled
                placeholder="加载中..."
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-500 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
              <input
                type="text"
                disabled
                placeholder="加载中..."
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-500 cursor-not-allowed"
              />
            </div>
          </div>
        </div>

        {/* 修改密码 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">修改密码</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">当前密码</label>
              <input
                type="password"
                placeholder="••••••••"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">新密码</label>
              <input
                type="password"
                placeholder="至少8位，含大小写字母、数字、特殊字符"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">确认新密码</label>
              <input
                type="password"
                placeholder="••••••••"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <button
              disabled
              className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg disabled:opacity-50 cursor-not-allowed"
            >
              更新密码（即将开放）
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add "frontend/app/(dashboard)/"
git commit -m "feat: 创建仪表盘/ETF/对话/设置四个页面骨架"
```

---

## Task 10: 创建 LoginRegisterForm 组件

**Files:**
- 创建: `frontend/components/auth/LoginRegisterForm.tsx`

- [ ] **Step 1: 创建组件**

```typescript
// frontend/components/auth/LoginRegisterForm.tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { login, register } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/auth'

type Tab = 'login' | 'register'

// 从 Axios 错误中提取后端 detail 消息
function getErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    const detail = axiosErr.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return '操作失败，请重试'
}

export default function LoginRegisterForm() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)

  const [tab, setTab] = useState<Tab>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const switchTab = (t: Tab) => {
    setTab(t)
    setError('')
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await login(email, password)
      // 登录响应不含用户信息，user 设为 null
      setAuth(res.access_token, null)
      router.push('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await register(email, password, username || undefined)
      // 注册响应含用户信息和 token
      setAuth(res.token.access_token, {
        id: res.id,
        email: res.email,
        username: res.username,
      })
      router.push('/dashboard')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8 w-full max-w-sm">
      {/* Tab 切换 */}
      <div className="flex mb-6 bg-gray-100 rounded-lg p-1">
        <button
          type="button"
          onClick={() => switchTab('login')}
          className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
            tab === 'login'
              ? 'bg-white shadow-sm text-gray-900'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          登录
        </button>
        <button
          type="button"
          onClick={() => switchTab('register')}
          className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
            tab === 'register'
              ? 'bg-white shadow-sm text-gray-900'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          注册
        </button>
      </div>

      {tab === 'login' ? (
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      ) : (
        <form onSubmit={handleRegister} className="flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              用户名 <span className="text-gray-400 font-normal">（可选）</span>
            </label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="昵称"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少8位，含大小写字母、数字、特殊字符"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '注册中...' : '注册'}
          </button>
        </form>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/components/auth/LoginRegisterForm.tsx
git commit -m "feat: 创建 LoginRegisterForm 组件（Tab 切换，对接登录/注册 API）"
```

---

## Task 11: 创建落地页并迁移路由

**Files:**
- 删除: `frontend/app/page.tsx`（旧默认模板）
- 创建: `frontend/app/(public)/page.tsx`

- [ ] **Step 1: 删除旧 page.tsx**

```bash
rm /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/page.tsx
```

- [ ] **Step 2: 创建 (public) 目录和落地页**

```bash
mkdir -p /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend/app/\(public\)
```

```typescript
// frontend/app/(public)/page.tsx
import LoginRegisterForm from '@/components/auth/LoginRegisterForm'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* 顶部导航（未登录态，无页面链接） */}
      <nav className="h-14 border-b border-gray-200 bg-white/80 backdrop-blur-sm px-6 flex items-center justify-between">
        <span className="font-bold text-gray-900 text-base">DeepAlpha</span>
        <div className="flex items-center gap-5 text-sm text-gray-500">
          <span>ETF 资金流</span>
          <span>功能介绍</span>
        </div>
      </nav>

      {/* Hero + 表单 */}
      <div className="max-w-6xl mx-auto px-6 pt-20 pb-16 flex items-center gap-16 flex-wrap">
        {/* 左侧：Hero 文案 */}
        <div className="flex-1 min-w-72 max-w-xl">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-600 text-xs font-medium px-3 py-1 rounded-full mb-6 border border-blue-100">
            AI 驱动的投资分析
          </div>
          <h1 className="text-4xl font-bold text-gray-900 leading-tight mb-4">
            AI 驱动的<br />投资决策平台
          </h1>
          <p className="text-lg text-gray-500 leading-relaxed mb-8">
            智能分析 ETF 资金流向，AI Agent 实时解读市场动态，助你把握投资机会。
          </p>
          <div className="flex gap-3 flex-wrap">
            <span className="px-5 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium cursor-default">
              免费开始
            </span>
            <span className="px-5 py-2.5 border border-gray-200 text-gray-700 rounded-lg text-sm font-medium cursor-default">
              了解更多
            </span>
          </div>
        </div>

        {/* 右侧：登录/注册表单 */}
        <div className="flex-shrink-0">
          <LoginRegisterForm />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。

- [ ] **Step 4: 启动开发服务器，手动验证**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npm run dev
```

打开 `http://localhost:3000`，验证：
- [ ] 落地页正常显示（Hero 文案 + 登录/注册表单）
- [ ] Tab 切换登录/注册正常
- [ ] 访问 `http://localhost:3000/dashboard` 自动重定向到 `/`（AuthGuard 生效）
- [ ] 注册新账号后跳转到 `/dashboard` 并显示仪表盘骨架
- [ ] 顶部导航显示，路由链接正常高亮
- [ ] 退出按钮清除状态并跳转到 `/`

- [ ] **Step 5: 停止开发服务器，提交**

```bash
# Ctrl+C 停止 dev server，然后：
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/app/
git commit -m "feat: 落地页（Hero + 登录/注册表单），完成 route group 迁移"
```

---

## Task 12: 全量 TypeScript 检查 + ESLint

- [ ] **Step 1: TypeScript 编译检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx tsc --noEmit
```

预期：无错误。若有错误，根据错误信息修复后再次运行。

- [ ] **Step 2: ESLint 检查**

```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai/frontend && npx eslint . --ext .ts,.tsx --max-warnings 0
```

预期：无错误，无警告。若有警告，修复后再次运行。

- [ ] **Step 3: 最终提交（若有修复）**

若前两步有修复：
```bash
cd /Users/zhangfang/PycharmProjects/deepalpha-club-ai
git add frontend/
git commit -m "fix: 修复 TypeScript/ESLint 检查问题"
```

若无修复，跳过。
