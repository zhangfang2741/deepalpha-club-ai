// frontend/lib/api/auth.ts
import apiClient from './client'

export interface AuthResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  email: string
  username?: string
  created_at: string
}

export const login = async (email: string, password: string): Promise<AuthResponse> => {
  // 后端 /auth/login 使用 OAuth2 form 格式
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)

  const response = await apiClient.post<AuthResponse>('/api/v1/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return response.data
}

export const register = async (email: string, password: string): Promise<User> => {
  const response = await apiClient.post<User>('/api/v1/auth/register', { email, password })
  return response.data
}

export const logout = async (): Promise<void> => {
  await apiClient.post('/api/v1/auth/logout')
}

export const getMe = async (): Promise<User> => {
  const response = await apiClient.get<User>('/api/v1/auth/me')
  return response.data
}
