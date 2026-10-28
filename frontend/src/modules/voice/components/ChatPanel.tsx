import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { BookOpen, GraduationCap, MessageCircle, RotateCcw, Send, Sparkles, X } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import { ChatMessage } from '@/shared/types'
import { CorrectionCategory, LearningState } from '@/shared/types/learning'
import { LiveTurn } from '@/shared/hooks/useVoiceSession'
import { cn } from '@/shared/lib/utils'

type TabId = 'conversation' | 'corrections' | 'vocabulary' | 'progress'

interface ChatPanelProps {
  open: boolean
  onClose: () => void
  messages: ChatMessage[]
  learning: LearningState
  liveTurns: LiveTurn[]
  isSending: boolean
  isLoadingHistory: boolean
  callActive: boolean
  onSend: (content: string) => Promise<void>
  onReset: () => Promise<void>
}

const CATEGORY_LABEL: Record<CorrectionCategory, string> = {
  grammar: 'Gramática',
  vocabulary: 'Vocabulario',
  naturalness: 'Naturalidad',
}

const CATEGORY_CLASS: Record<CorrectionCategory, string> = {
  grammar: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  vocabulary: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  naturalness: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
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

function EmptyState({ icon: Icon, title, hint }: { icon: any; title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 px-6 text-center">
      <Icon className="h-8 w-8 text-muted-foreground/60" />
      <p className="font-medium">{title}</p>
      <p className="text-sm text-muted-foreground">{hint}</p>
    </div>
  )
}

function CorrectionsTab({ learning }: { learning: LearningState }) {
  if (!learning.enabled) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="Correcciones desactivadas"
        hint="El servidor tiene el análisis desactivado (LEARNING_ENABLED=false)."
      />
    )
  }
  if (learning.corrections.length === 0) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="Sin correcciones todavía"
        hint="Habla o escribe en inglés y aquí verás los errores con su explicación."
      />
    )
  }
  return (
    <div className="space-y-3 px-4 py-4">
      {[...learning.corrections].reverse().map((correction) => (
        <article key={correction.id} className="rounded-2xl border p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span
              className={cn(
                'text-[11px] font-medium px-2 py-0.5 rounded-full',
                CATEGORY_CLASS[correction.category],
              )}
            >
              {CATEGORY_LABEL[correction.category]}
            </span>
            <span className="text-[11px] text-muted-foreground">Turno {correction.turn}</span>
          </div>
          <p className="text-sm space-x-2">
            <span className="text-muted-foreground line-through">{correction.original}</span>
            <span aria-hidden className="text-muted-foreground">
              →
            </span>
            <span className="font-medium text-emerald-600 dark:text-emerald-400">
              {correction.corrected}
            </span>
          </p>
          <p className="text-sm text-muted-foreground">{correction.explanation}</p>
        </article>
      ))}
    </div>
  )
}

function VocabularyTab({ learning }: { learning: LearningState }) {
  if (!learning.enabled) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Vocabulario desactivado"
        hint="El servidor tiene el análisis desactivado (LEARNING_ENABLED=false)."
      />
    )
  }
  if (learning.vocabulary.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Sin vocabulario todavía"
        hint="Cada conversación añade palabras y expresiones útiles."
      />
    )
  }
  return (
    <div className="space-y-3 px-4 py-4">
      {[...learning.vocabulary].reverse().map((item) => (
        <article key={item.id} className="rounded-2xl border p-3 space-y-1">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="font-medium">{item.term}</h3>
            <span className="text-[11px] text-muted-foreground">Turno {item.turn}</span>
          </div>
          <p className="text-sm">{item.meaning}</p>
          <p className="text-sm italic text-muted-foreground">{item.example}</p>
        </article>
      ))}
    </div>
  )
}

function ProgressTab({ learning }: { learning: LearningState }) {
  const { progress } = learning
  const max = Math.max(1, ...Object.values(progress.by_category))
  const stats = [
    { label: 'Turnos', value: progress.turns },
    { label: 'Correcciones', value: progress.corrections },
    { label: 'Palabras', value: progress.vocabulary },
  ]

  return (
    <div className="px-4 py-4 space-y-6">
      <div className="grid grid-cols-3 gap-2">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-2xl border p-3 text-center">
            <p className="text-2xl font-semibold tabular-nums">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-medium">Correcciones por tipo</h3>
        {(Object.keys(CATEGORY_LABEL) as CorrectionCategory[]).map((category) => {
          const value = progress.by_category[category] ?? 0
          return (
            <div key={category} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span>{CATEGORY_LABEL[category]}</span>
                <span className="tabular-nums text-muted-foreground">{value}</span>
              </div>
              <div className="h-2 rounded-full bg-secondary overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${(value / max) * 100}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>

      {!learning.enabled && (
        <p className="text-xs text-muted-foreground">
          El análisis está desactivado en el servidor: solo se cuentan las conversaciones.
        </p>
      )}
    </div>
  )
}

export function ChatPanel({
  open,
  onClose,
  messages,
  learning,
  liveTurns,
  isSending,
  isLoadingHistory,
  callActive,
  onSend,
  onReset,
}: ChatPanelProps) {
  const isDesktop = useIsDesktop()
  const [input, setInput] = useState('')
  const [tab, setTab] = useState<TabId>('conversation')
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
    if (open && tab === 'conversation') endRef.current?.scrollIntoView({ block: 'end' })
  }, [open, tab, messages, liveTurns, isSending])

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

  const tabs: { id: TabId; label: string; icon: any; count?: number }[] = [
    { id: 'conversation', label: 'Conversación', icon: MessageCircle },
    { id: 'corrections', label: 'Correcciones', icon: GraduationCap, count: learning.corrections.length },
    { id: 'vocabulary', label: 'Vocabulario', icon: BookOpen, count: learning.vocabulary.length },
    { id: 'progress', label: 'Progreso', icon: Sparkles },
  ]

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
            aria-label="Conversación y progreso"
            className={cn(
              'flex flex-col bg-background overflow-hidden',
              isDesktop
                ? 'h-full flex-shrink-0 border-l'
                : 'fixed inset-x-0 bottom-0 top-12 z-50 rounded-t-3xl border-t shadow-2xl',
            )}
          >
            <div className={cn('flex flex-col h-full', isDesktop && 'w-[420px]')}>
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <h2 className="font-semibold">Tu inglés</h2>
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

              <div role="tablist" className="flex border-b px-2">
                {tabs.map(({ id, label, icon: Icon, count }) => (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={tab === id}
                    onClick={() => setTab(id)}
                    className={cn(
                      'flex-1 flex flex-col items-center gap-1 py-2 text-[11px] border-b-2 transition-colors',
                      tab === id
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <span className="relative">
                      <Icon className="h-4 w-4" />
                      {count !== undefined && count > 0 && (
                        <span className="absolute -top-1.5 -right-2 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] leading-4 tabular-nums">
                          {count > 99 ? '99+' : count}
                        </span>
                      )}
                    </span>
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex-1 overflow-y-auto">
                {tab === 'conversation' && (
                  <div className="px-4 py-4 space-y-3">
                    {isLoadingHistory && messages.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center">
                        Cargando historial...
                      </p>
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
                )}
                {tab === 'corrections' && <CorrectionsTab learning={learning} />}
                {tab === 'vocabulary' && <VocabularyTab learning={learning} />}
                {tab === 'progress' && <ProgressTab learning={learning} />}
              </div>

              {tab === 'conversation' && (
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
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
