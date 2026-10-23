import { useState } from 'react'
import { Search, MessageSquare } from 'lucide-react'
import { Input } from '@/shared/ui/input'
import { ScrollArea } from '@/shared/ui/scroll-area'
import { motion } from 'motion/react'
import { Conversation } from '@/shared/types'
import { formatDistanceToNow } from 'date-fns'
import { es } from 'date-fns/locale'

const mockConversations: Conversation[] = [
  {
    id: '1',
    title: 'Conversación sobre gramática',
    lastMessage: 'Practiquemos los tiempos verbales...',
    updatedAt: Date.now() - 3600000,
  },
  {
    id: '2',
    title: 'Práctica de conversación',
    lastMessage: 'How can I help you today?',
    updatedAt: Date.now() - 86400000,
  },
  {
    id: '3',
    title: 'Vocabulario de negocios',
    lastMessage: 'Let\'s learn some business terms',
    updatedAt: Date.now() - 172800000,
  },
]

export function HistoryPage() {
  const [search, setSearch] = useState('')

  const filtered = mockConversations.filter(
    (conv) =>
      conv.title.toLowerCase().includes(search.toLowerCase()) ||
      conv.lastMessage.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="max-w-4xl mx-auto p-4 md:p-6 space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold mb-2">Historial</h1>
        <p className="text-muted-foreground">Tus conversaciones anteriores</p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Buscar conversaciones..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9 rounded-2xl"
        />
      </div>

      <ScrollArea className="h-[calc(100vh-20rem)] md:h-[calc(100vh-18rem)]">
        <div className="space-y-2">
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No se encontraron conversaciones
            </div>
          ) : (
            filtered.map((conv, index) => (
              <motion.button
                key={conv.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="w-full text-left p-4 rounded-2xl border bg-card hover:bg-accent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                aria-label={`Abrir conversación: ${conv.title}`}
              >
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-full bg-primary/10">
                    <MessageSquare className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <h3 className="font-semibold truncate">{conv.title}</h3>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatDistanceToNow(conv.updatedAt, { addSuffix: true, locale: es })}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">{conv.lastMessage}</p>
                  </div>
                </div>
              </motion.button>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
