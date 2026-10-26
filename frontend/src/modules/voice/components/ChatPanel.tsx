import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { RotateCcw, Send, X } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import { ChatMessage } from '@/shared/types'
import { LiveTurn } from '@/shared/hooks/useVoiceSession'
import { cn } from '@/shared/lib/utils'

interface ChatPanelProps {
  open: boolean
  onClose: () => void
  messages: ChatMessage[]
  liveTurns: LiveTurn[]
  isSending: boolean
  isLoadingHistory: boolean
  callActive: boolean
  onSend: (content: string) => Promise<void>
  onReset: () => Promise<void>
}

function useIsDesktop(): boolean {
  const query = '(min-width: 768px)'
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = () => setMatches(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  return matches
}

function Bubble({ role, text, live }: { role: 'user' | 'assistant'; text: string; live?: boolean }) {
  return (
    <div className={cn('flex', role === 'user' ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] px-4 py-2 rounded-3xl',
          role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-secondary',
          live && 'ring-1 ring-primary/30',
        )}
      >
        <p className="text-sm whitespace-pre-wrap">{text}</p>
      </div>
    </div>
  )
}

export function ChatPanel({
  open,
  onClose,
  messages,
  liveTurns,
  isSending,
  isLoadingHistory,
  callActive,
  onSend,
  onReset,
}: ChatPanelProps) {
  const isDesktop = useIsDesktop()
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: 'end' })
  }, [open, messages, liveTurns, isSending])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isSending) return
    setInput('')
    await onSend(text)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  const variants = isDesktop
    ? {
        initial: { width: 0, opacity: 0 },
        animate: { width: 420, opacity: 1 },
        exit: { width: 0, opacity: 0 },
      }
    : {
        initial: { y: '100%' },
        animate: { y: 0 },
        exit: { y: '100%' },
      }

  return (
    <AnimatePresence>
      {open && (
        <>
          {!isDesktop && (
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
              className="fixed inset-0 z-40 bg-black/40"
            />
          )}
          <motion.aside
            key="panel"
            {...variants}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            aria-label="Historial de la conversación"
            className={cn(
              'flex flex-col bg-background overflow-hidden',
              isDesktop
                ? 'h-full flex-shrink-0 border-l'
                : 'fixed inset-x-0 bottom-0 top-12 z-50 rounded-t-3xl border-t shadow-2xl',
            )}
          >
            <div className={cn('flex flex-col h-full', isDesktop && 'w-[420px]')}>
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <h2 className="font-semibold">Conversación</h2>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void onReset()}
                    disabled={isSending || callActive}
                    className="rounded-full text-muted-foreground"
                  >
                    <RotateCcw className="h-4 w-4 mr-2" />
                    Nueva
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={onClose}
                    className="rounded-full"
                    aria-label="Cerrar chat"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                {isLoadingHistory && messages.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center">Cargando historial...</p>
                )}
                {messages.map((message) => (
                  <Bubble key={message.id} role={message.role} text={message.content} />
                ))}
                {liveTurns
                  .filter((turn) => turn.text)
                  .map((turn) => (
                    <Bubble key={turn.id} role={turn.role} text={turn.text} live />
                  ))}
                {isSending && (
                  <div className="flex justify-start">
                    <div className="px-4 py-3 rounded-3xl bg-secondary flex gap-1">
                      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" />
                    </div>
                  </div>
                )}
                <div ref={endRef} />
              </div>

              <div className="border-t p-3 space-y-2">
                {callActive && (
                  <p className="text-xs text-muted-foreground px-1">
                    Llamada en curso. Al enviar un mensaje escrito, la llamada se terminará.
                  </p>
                )}
                <div className="flex gap-2 items-end">
                  <Textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Escribe un mensaje..."
                    className="min-h-[48px] max-h-[160px] resize-none rounded-2xl"
                    rows={1}
                  />
                  <Button
                    onClick={() => void handleSend()}
                    disabled={!input.trim() || isSending}
                    size="icon"
                    className="rounded-full h-11 w-11 flex-shrink-0"
                    aria-label="Enviar mensaje"
                  >
                    <Send className="h-5 w-5" />
                  </Button>
                </div>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
