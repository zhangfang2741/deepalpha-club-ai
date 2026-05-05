# DeepAlpha 前端 App 框架设计文档

**日期：** 2026-05-05
**状态：** 已批准，待实施

---

## 概述

为 deepalpha-club-ai 构建前端 App 整体框架，包含落地页、认证流程（真实对接后端 API）、顶部导航、以及四个受保护页面的基础骨架（仪表盘、ETF 资金流、AI 对话、个人设置）。

**技术栈：** Next.js 16 App Router + TypeScript + Tailwind CSS v4 + @base-ui/react (shadcn) + Zustand + Axios

---

## 设计决策

| 维度 | 选择 | 原因 |
|---|---|---|
| 导航结构 | 顶部导航栏 | 简洁直观，页面数量适中 |
| 认证入口 | 落地页 + 右侧嵌入登录表单 | 减少跳转，一屏完成转化 |
| 视觉风格 | 明亮简约（白底 + 深色文字 + 蓝色点缀） | 清晰易读，适合高频使用 |
| 架构方案 | Route Groups + 客户端 AuthGuard | 职责清晰，标准 App Router 模式 |
| JWT 存储 | localStorage（遵循项目规范） | 与后端约定一致 |

---

## 目录结构

```
frontend/
├── app/
│   ├── (public)/
│   │   └── page.tsx              # 落地页（Hero + 右侧登录/注册表单）
│   ├── (dashboard)/
│   │   ├── layout.tsx            # AuthGuard + TopNav + 内容区
│   │   ├── dashboard/
│   │   │   └── page.tsx          # 仪表盘骨架
│   │   ├── etf/
│   │   │   └── page.tsx          # ETF 资金流骨架
│   │   ├── chat/
│   │   │   └── page.tsx          # AI 对话骨架
│   │   └── settings/
│   │       └── page.tsx          # 个人设置骨架
│   ├── layout.tsx                # 根布局（字体、全局 CSS、Providers）
│   └── globals.css
├── components/
│   ├── auth/
│   │   ├── AuthGuard.tsx         # 检查登录态，未登录重定向到 /
│   │   └── LoginRegisterForm.tsx # 登录/注册 Tab 表单
│   ├── layout/
│   │   └── TopNav.tsx            # 顶部导航组件
│   └── ui/                       # shadcn/ui 组件
├── lib/
│   ├── api/
│   │   ├── client.ts             # Axios 实例（补充请求拦截器）
│   │   └── auth.ts               # 认证 API（login/register）
│   └── store/
│       └── auth.ts               # Zustand 认证状态（补充 hydrate）
└── .env.local                    # NEXT_PUBLIC_API_URL
```

---

## 路由规划

| URL | 文件 | 访问控制 |
|---|---|---|
| `/` | `(public)/page.tsx` | 公开 |
| `/dashboard` | `(dashboard)/dashboard/page.tsx` | 需登录 |
| `/etf` | `(dashboard)/etf/page.tsx` | 需登录 |
| `/chat` | `(dashboard)/chat/page.tsx` | 需登录 |
| `/settings` | `(dashboard)/settings/page.tsx` | 需登录 |

---

## 认证流程

### 登录数据流

```
用户填写表单
    ↓
LoginRegisterForm → POST /api/v1/auth/login
    ↓ 成功
后端返回 { access_token, user }
    ↓
store.setAuth(token, user) + localStorage.setItem('token', token)
    ↓
router.push('/dashboard')
```

### 退出登录

```
TopNav 退出按钮
    ↓
store.clearAuth() + localStorage.removeItem('token')
    ↓
router.push('/')
```

### 页面刷新恢复状态

```
AuthGuard 挂载
    ↓
store.hydrate()  ← 从 localStorage 读取 token
    ↓
有 token → 渲染子页面
无 token → router.push('/')
```

---

## 核心组件规格

### Zustand AuthStore（`lib/store/auth.ts`）

```ts
interface AuthState {
  user: { id: number; email: string; username: string } | null
  token: string | null
  isAuthenticated: boolean
  setAuth: (token: string, user: AuthState['user']) => void
  clearAuth: () => void
  hydrate: () => void  // 从 localStorage 恢复
}
```

### Axios 客户端（`lib/api/client.ts`）

- baseURL：`process.env.NEXT_PUBLIC_API_URL`
- 请求拦截器：从 Zustand store 读取 token，附加 `Authorization: Bearer <token>`
- 响应拦截器：401 时调用 `clearAuth()` 并跳转到 `/`

### AuthGuard（`components/auth/AuthGuard.tsx`）

- 客户端组件（`'use client'`）
- 挂载时调用 `hydrate()`，检查 `isAuthenticated`
- 未认证时 `router.push('/')`，认证后渲染 `children`
- 在检查期间显示加载状态（避免闪烁）

### LoginRegisterForm（`components/auth/LoginRegisterForm.tsx`）

- Tab 切换：登录 / 注册
- 登录字段：邮箱、密码
- 注册字段：用户名、邮箱、密码
- 错误提示显示在表单内
- 成功后调用 `setAuth` 并跳转

### TopNav（`components/layout/TopNav.tsx`）

- Logo + "DeepAlpha" 文字（链接到 `/dashboard`）
- 导航链接：仪表盘 / ETF 资金流 / AI 对话 / 设置（使用 `usePathname` 高亮当前页）
- 右侧：用户名 + 退出按钮
- 样式：白色背景，底部 border，蓝色高亮当前页

---

## 落地页设计（`(public)/page.tsx`）

**布局：** 两栏（左: Hero 文案，右: 登录/注册表单）

**Hero 文案（左侧）：**
- 标题：AI 驱动的投资决策平台
- 副标题：智能分析 ETF 资金流向，AI Agent 实时解读市场动态
- CTA 按钮：免费开始 / 了解更多

**右侧：** `LoginRegisterForm` 组件（白色卡片样式）

---

## 各页面骨架内容

| 页面 | 骨架内容 |
|---|---|
| `/dashboard` | 页面标题 + 3 个数据占位卡 + 1 个占位图表区 |
| `/etf` | 页面标题 + "ETF 资金流数据功能即将上线" 占位提示 |
| `/chat` | 聊天气泡区（空状态提示）+ 底部输入框（UI 骨架，不接 API） |
| `/settings` | 账户信息区（邮箱只读）+ 修改密码表单（字段 + 按钮，不接 API） |

---

## 范围边界

**本次包含：**
- 完整目录结构和路由
- 落地页 UI（Hero + 登录/注册表单）
- 真实认证对接（login/register API）
- 顶部导航（含路由高亮）
- 四个页面骨架

**不包含：**
- ETF、Chat、Settings 页面的真实数据对接
- 响应式移动端适配
- 深色模式
- 邮件验证、忘记密码等扩展认证功能

---

## 后端 API 依赖

| 接口 | 方法 | 路径 |
|---|---|---|
| 登录 | POST | `/api/v1/auth/login` |
| 注册 | POST | `/api/v1/auth/register` |

请求/响应格式以后端实际文档为准。
