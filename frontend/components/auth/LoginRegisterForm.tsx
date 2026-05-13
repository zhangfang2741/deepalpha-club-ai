'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { login, register } from '@/lib/api/auth'
import { useAuthStore } from '@/lib/store/auth'

type Tab = 'login' | 'register'

// 从 Axios 错误中提取后端 detail 消息
function getErrorMessage(err: unknown): string {
  // Case 1: Axios error with response
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as {
      response?: {
        data?: Record<string, unknown>
      }
      status?: number
    }
    const data = axiosErr.response?.data

    if (data && typeof data === 'object') {
      // 1. FastAPI standard: error info is usually in 'detail'
      const detail = data.detail

      if (typeof detail === 'string') {
        return detail
      }

      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        if ('message' in detail && typeof detail.message === 'string') {
          return detail.message
        }
      }

      // Handle standard FastAPI validation errors (detail is array)
      if (Array.isArray(detail)) {
        return detail
          .map((item) => {
            const loc = item.loc || []
            const field = loc[loc.length - 1] || '字段'
            let msg = item.msg || '无效值'

            if (item.type === 'string_too_short') msg = `长度不足`
            else if (item.type === 'missing') msg = `必填`
            else if (item.type === 'type_error') msg = `类型错误`
            else if (item.type === 'value_error.email' || msg.includes('email')) msg = `邮箱格式不正确`
            else if (msg.includes('uppercase')) msg = '需包含大写字母'
            else if (msg.includes('lowercase')) msg = '需包含小写字母'
            else if (msg.includes('number')) msg = '需包含数字'
            else if (msg.includes('special character')) msg = '需包含特殊字符'

            const fieldMap: Record<string, string> = {
              email: '邮箱',
              password: '密码',
              username: '用户名',
            }
            const translatedField = fieldMap[field] || field

            return `${translatedField}: ${msg}`
          })
          .join('\n')
      }

      // 2. Custom validation errors from app/main.py
      if (Array.isArray(data.errors)) {
        return (data.errors as Array<Record<string, string>>)
          .map((e) => {
            const field = e.field || ''
            let message = e.message || '无效值'

            // Basic translation for pydantic errors
            if (message.includes('value is not a valid email address')) message = '邮箱格式不正确'
            else if (message.includes('field required')) message = '必填'
            else if (message.includes('at least')) message = '长度不足'
            else if (message.includes('uppercase')) message = '需包含大写字母'
            else if (message.includes('lowercase')) message = '需包含小写字母'
            else if (message.includes('number')) message = '需包含数字'
            else if (message.includes('special character')) message = '需包含特殊字符'

            const fieldMap: Record<string, string> = {
              email: '邮箱',
              password: '密码',
              username: '用户名',
            }
            const translatedField = fieldMap[field] || field

            return translatedField ? `${translatedField}: ${message}` : message
          })
          .join('\n')
      }

      // 3. Fallback to top-level message or error
      if (typeof data.message === 'string') return data.message
      if (typeof data.error === 'string') return data.error
    }

    if (axiosErr.status === 401) return '邮箱或密码错误'
    if (axiosErr.status === 403) return '无权访问此资源'
    if (axiosErr.status === 429) return '请求过于频繁，请稍后再试'
  }

  if (err && typeof err === 'object' && 'message' in err) {
    const msg = (err as { message: string }).message
    if (msg.includes('Network') || msg.includes('network')) return '网络连接失败，请检查网络'
    if (msg.includes('timeout') || msg.includes('Timeout')) return '请求超时，请稍后重试'
  }

  return '操作失败，请稍后重试'
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

  const inputClass =
    'w-full px-3.5 py-2.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors'

  const labelClass = 'block text-xs font-medium text-slate-500 mb-1.5 uppercase tracking-wide'

  return (
    <div className="bg-white rounded-2xl border border-blue-100 p-8 w-full shadow-xl shadow-blue-900/[0.08]">
      {/* 表单标题 */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-slate-900">
          {tab === 'login' ? '欢迎回来' : '创建账号'}
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          {tab === 'login' ? '登录以访问你的投资分析面板' : '免费注册，开始智能投资分析'}
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex mb-6 bg-slate-100 rounded-lg p-1 border border-slate-200">
        <button
          type="button"
          onClick={() => switchTab('login')}
          className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
            tab === 'login'
              ? 'bg-white text-blue-600 shadow-sm border border-slate-200'
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          登录
        </button>
        <button
          type="button"
          onClick={() => switchTab('register')}
          className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
            tab === 'register'
              ? 'bg-white text-blue-600 shadow-sm border border-slate-200'
              : 'text-slate-400 hover:text-slate-600'
          }`}
        >
          注册
        </button>
      </div>

      {tab === 'login' ? (
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <label className={labelClass}>邮箱</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
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
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
              <p className="text-sm text-red-400 whitespace-pre-line">{error}</p>
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-1 shadow-sm shadow-blue-600/20"
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      ) : (
        <form onSubmit={handleRegister} className="flex flex-col gap-4">
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
            <label className={labelClass}>邮箱</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
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
          </div>
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
              <p className="text-sm text-red-400 whitespace-pre-line">{error}</p>
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-1 shadow-sm shadow-blue-600/20"
          >
            {loading ? '注册中...' : '注册'}
          </button>
        </form>
      )}
    </div>
  )
}
