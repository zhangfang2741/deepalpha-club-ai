import apiClient from './client'

export const PREFERRED_MODEL_STORAGE_KEY = 'preferred_model'

export interface ModelsResponse {
  provider: string
  default: string
  current: string | null
  available: string[]
}

export async function getModels(): Promise<ModelsResponse> {
  const { data } = await apiClient.get<ModelsResponse>('/api/v1/settings/models')
  if (typeof window !== 'undefined') {
    if (data.current) localStorage.setItem(PREFERRED_MODEL_STORAGE_KEY, data.current)
    else localStorage.removeItem(PREFERRED_MODEL_STORAGE_KEY)
  }
  return data
}

// model 传 null / 空串表示清除偏好（跟随系统默认）
export async function setPreferredModel(model: string | null): Promise<ModelsResponse> {
  const { data } = await apiClient.put<ModelsResponse>('/api/v1/settings/preferred-model', {
    model: model || null,
  })
  if (typeof window !== 'undefined') {
    if (data.current) localStorage.setItem(PREFERRED_MODEL_STORAGE_KEY, data.current)
    else localStorage.removeItem(PREFERRED_MODEL_STORAGE_KEY)
  }
  return data
}

// 品牌名规范化：让下拉里的模型名风格统一（MiniMax / GPT / Claude / Gemini）
const BRAND_MAP: Record<string, string> = {
  minimax: 'MiniMax',
  gpt: 'GPT',
  claude: 'Claude',
  gemini: 'Gemini',
}

function capitalize(segment: string): string {
  if (!segment) return segment
  // 版本段如 m2.7 → M2.7；其余首字母大写
  if (/^m\d/.test(segment)) return segment.toUpperCase()
  return segment[0].toUpperCase() + segment.slice(1)
}

/** 把注册名（全小写、连字符）格式化为统一的展示标签，如 minimax-m2.7-highspeed → MiniMax M2.7 Highspeed。 */
export function formatModelLabel(name: string): string {
  const parts = name.split('-')
  const brand = BRAND_MAP[parts[0]?.toLowerCase() ?? '']
  if (!brand) {
    return parts.map(capitalize).join(' ')
  }
  return [brand, ...parts.slice(1).map(capitalize)].join(' ')
}
