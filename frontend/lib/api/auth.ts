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
