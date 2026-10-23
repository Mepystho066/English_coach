export type ModuleId = 'voice' | 'chat' | 'history' | 'settings'

export interface ModuleDef {
  id: ModuleId
  title: string
  icon: any
  path: string
  component: React.ComponentType
}

export type VoiceSessionState =
  | 'idle'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'interrupted'

export interface TranscriptEntry {
  id: string
  role: 'user' | 'assistant'
  text: string
  partial?: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export interface Conversation {
  id: string
  title: string
  lastMessage: string
  updatedAt: number
}
