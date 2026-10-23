import { Mic, MessageSquare, History, Settings } from 'lucide-react'
import { ModuleDef } from '@/shared/types'
import { VoicePage } from '@/modules/voice/VoicePage'
import { ChatPage } from '@/modules/chat/ChatPage'
import { HistoryPage } from '@/modules/history/HistoryPage'
import { SettingsPage } from '@/modules/settings/SettingsPage'

export const modules: ModuleDef[] = [
  {
    id: 'voice',
    title: 'Voz',
    icon: Mic,
    path: '/',
    component: VoicePage,
  },
  {
    id: 'chat',
    title: 'Chat',
    icon: MessageSquare,
    path: '/chat',
    component: ChatPage,
  },
  {
    id: 'history',
    title: 'Historial',
    icon: History,
    path: '/history',
    component: HistoryPage,
  },
  {
    id: 'settings',
    title: 'Ajustes',
    icon: Settings,
    path: '/settings',
    component: SettingsPage,
  },
]

export function getModule(id: string) {
  return modules.find((m) => m.id === id)
}
