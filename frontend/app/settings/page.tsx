'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ListChecks } from 'lucide-react'
import { getUserProfile, updateUserProfile, changePassword, type UserProfileResponse } from '@/lib/api/auth'
import DashboardShell from '@/components/layout/DashboardShell'

// 从 Axios 风格错误中安全提取后端返回的 detail 字段
const getErrorDetail = (err: unknown): unknown =>
  (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Profile form state
  const [username, setUsername] = useState('')

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordLoading, setPasswordLoading] = useState(false)

  // Format date
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  // Load user profile
  useEffect(() => {
    const loadProfile = async () => {
      try {
        const data = await getUserProfile()
        setProfile(data)
        setUsername(data.username || '')
      } catch (err) {
        setError('加载用户资料失败，请刷新页面重试')
        console.error('Failed to load profile:', err)
      } finally {
        setLoading(false)
      }
    }

    loadProfile()
  }, [])

  // Handle profile update
  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setSaving(true)

    try {
      const updated = await updateUserProfile({ username: username || null })
      setProfile(updated)
      setSuccess('个人资料已更新')
    } catch (err) {
      const detail = getErrorDetail(err)
      setError(typeof detail === 'string' ? detail : '更新失败，请稍后重试')
      console.error('Failed to update profile:', err)
    } finally {
      setSaving(false)
    }
  }

  // Handle password change
  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError(null)

    // Validate passwords match
    if (newPassword !== confirmPassword) {
      setPasswordError('两次输入的密码不一致')
      return
    }

    // Validate password requirements
    if (newPassword.length < 8) {
      setPasswordError('密码长度至少8位')
      return
    }
    if (!/[A-Z]/.test(newPassword)) {
      setPasswordError('密码必须包含至少一个大写字母')
      return
    }
    if (!/[a-z]/.test(newPassword)) {
      setPasswordError('密码必须包含至少一个小写字母')
      return
    }
    if (!/[0-9]/.test(newPassword)) {
      setPasswordError('密码必须包含至少一个数字')
      return
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(newPassword)) {
      setPasswordError('密码必须包含至少一个特殊字符')
      return
    }

    setPasswordLoading(true)

    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword
      })
      setSuccess('密码修改成功')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      const detail = getErrorDetail(err)
      if (detail && typeof detail === 'object' && 'message' in detail) {
        setPasswordError(String((detail as { message: unknown }).message))
      } else {
        setPasswordError(typeof detail === 'string' ? detail : '密码修改失败，请稍后重试')
      }
      console.error('Failed to change password:', err)
    } finally {
      setPasswordLoading(false)
    }
  }

  if (loading) {
    return (
      <DashboardShell>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">个人设置</h1>
        <div className="max-w-xl space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="animate-pulse space-y-4">
              <div className="h-4 bg-gray-200 rounded w-1/4"></div>
              <div className="h-10 bg-gray-200 rounded"></div>
              <div className="h-4 bg-gray-200 rounded w-1/4"></div>
              <div className="h-10 bg-gray-200 rounded"></div>
            </div>
          </div>
        </div>
      </DashboardShell>
    )
  }

  return (
    <DashboardShell>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">个人设置</h1>

      {/* Success message */}
      {success && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-700">{success}</p>
        </div>
      )}

      {/* Error message */}
      {(error || passwordError) && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-700">{error || passwordError}</p>
        </div>
      )}

      <div className="max-w-xl space-y-6">
        {/* Account Information */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">账户信息</h2>
          <form onSubmit={handleProfileSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
              <input
                type="email"
                value={profile?.email || ''}
                disabled
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-500 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="输入用户名"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">注册时间</label>
              <input
                type="text"
                value={profile?.created_at ? formatDate(profile.created_at) : '-'}
                disabled
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-500 cursor-not-allowed"
              />
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? '保存中...' : '保存修改'}
            </button>
          </form>
        </div>

        {/* Change Password */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">修改密码</h2>
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">当前密码</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">新密码</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="至少8位，含大小写字母、数字、特殊字符"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">确认新密码</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={passwordLoading}
              className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {passwordLoading ? '修改中...' : '修改密码'}
            </button>
          </form>
        </div>

        {/* System / Task Management */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-1">系统管理</h2>
          <p className="text-sm text-gray-500 mb-4">查看后台批量任务的运行情况，失败任务可在此继续。</p>
          <Link
            href="/supply-graph/tasks"
            className="flex items-center justify-between rounded-lg border border-gray-200 p-4 transition-colors hover:bg-gray-50"
          >
            <span className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                <ListChecks className="h-5 w-5" aria-hidden="true" />
              </span>
              <span>
                <span className="block text-sm font-medium text-gray-900">供应链任务看板</span>
                <span className="block text-xs text-gray-500">批次进度、配额等待与失败重试一览</span>
              </span>
            </span>
            <span className="text-gray-400" aria-hidden="true">›</span>
          </Link>
        </div>
      </div>
    </DashboardShell>
  )
}