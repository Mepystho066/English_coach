import { Mic, MicOff, Pause, Play, Square, MessageSquare } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import { VoiceSessionState } from '@/shared/types'

interface VoiceControlsProps {
  state: VoiceSessionState
  isMuted: boolean
  isPaused: boolean
  onToggleMute: () => void
  onTogglePause: () => void
  onStop: () => void
  isChatOpen: boolean
  onToggleChat: () => void
}

export function VoiceControls({
  state,
  isMuted,
  isPaused,
  onToggleMute,
  onTogglePause,
  onStop,
  isChatOpen,
  onToggleChat,
}: VoiceControlsProps) {
  const isActive = state !== 'idle'

  return (
    <div className="flex items-center gap-2 md:gap-3 flex-wrap justify-center px-4">
      {isActive && (
        <>
          <Button
            variant="outline"
            size="icon"
            onClick={onToggleMute}
            className={cn(
              'rounded-full h-12 w-12',
              isMuted && 'bg-destructive/10 border-destructive/50'
            )}
            aria-label={isMuted ? 'Activar micrófono' : 'Silenciar micrófono'}
          >
            {isMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </Button>

          <Button
            variant="outline"
            size="icon"
            onClick={onTogglePause}
            className="rounded-full h-12 w-12"
            aria-label={isPaused ? 'Reanudar' : 'Pausar'}
          >
            {isPaused ? <Play className="h-5 w-5" /> : <Pause className="h-5 w-5" />}
          </Button>

          <Button
            variant="destructive"
            size="icon"
            onClick={onStop}
            className="rounded-full h-12 w-12"
            aria-label="Terminar sesión"
          >
            <Square className="h-5 w-5" />
          </Button>
        </>
      )}

      <Button
        variant={isChatOpen ? 'default' : 'secondary'}
        onClick={onToggleChat}
        className="rounded-full h-12 px-6"
        aria-label={isChatOpen ? 'Cerrar chat' : 'Abrir chat'}
        aria-pressed={isChatOpen}
      >
        <MessageSquare className="h-5 w-5 mr-2" />
        <span>{isChatOpen ? 'Cerrar chat' : 'Chat'}</span>
      </Button>
    </div>
  )
}
