import { Mic } from 'lucide-react'
import { ModuleDef } from '@/shared/types'
import { VoicePage } from '@/modules/voice/VoicePage'

export const modules: ModuleDef[] = [
  {
    id: 'voice',
    title: 'Voz',
    icon: Mic,
    path: '/',
    component: VoicePage,
  },
]

export function getModule(id: string) {
  return modules.find((m) => m.id === id)
}
