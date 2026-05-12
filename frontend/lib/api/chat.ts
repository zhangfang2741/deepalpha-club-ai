import apiClient from './client'

export interface BackendChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export async function getChatHistory(): Promise<BackendChatMessage[]> {
  const { data } = await apiClient.get<{ messages: BackendChatMessage[] }>('/api/v1/messages')
  return data.messages ?? []
}

export async function clearChatHistory(): Promise<void> {
  await apiClient.delete('/api/v1/messages')
}
