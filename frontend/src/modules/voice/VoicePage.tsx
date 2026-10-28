import { useCallback, useEffect, useRef, useState } from 'react'
import { VoiceOrb } from './components/VoiceOrb'
import { LiveTranscript } from './components/LiveTranscript'
import { VoiceControls } from './components/VoiceControls'
import { StatusChips } from './components/StatusChips'
import { VoiceIndicators } from './components/VoiceIndicators'
import { ChatPanel } from './components/ChatPanel'
import { motion } from 'motion/react'
import { useVoiceSession } from '@/shared/hooks/useVoiceSession'
import { useChatRuntime } from '@/shared/hooks/useChatRuntime'

// The server saves a call's history a moment after the socket closes.
const HISTORY_SETTLE_MS = 1200

export function VoicePage() {
  const chat = useChatRuntime()
  const { refresh, applyLearning } = chat

  const {
    state,
    isMuted,
    isPaused,
    volume,
    userTranscript,
    assistantTranscript,
    liveTurns,
    statusChips,
    micPermission,
    connectionQuality,
    start,
    stop,
    toggleMute,
    togglePause,
    interrupt,
  } = useVoiceSession({ onLearningState: applyLearning })

  const [isChatOpen, setIsChatOpen] = useState(false)
  const [showLive, setShowLive] = useState(false)
  const wasActive = useRef(false)

  const callActive = state !== 'idle'

  // Keep the call's turns visible until the stored history has caught up.
  useEffect(() => {
    if (callActive) {
      wasActive.current = true
      setShowLive(true)
      return
    }
    if (!wasActive.current) return
    wasActive.current = false
    const timer = window.setTimeout(() => {
      void refresh().finally(() => setShowLive(false))
    }, HISTORY_SETTLE_MS)
    return () => window.clearTimeout(timer)
  }, [callActive, refresh])

  useEffect(() => {
    if (isChatOpen) void refresh()
  }, [isChatOpen, refresh])

  const handleOrbClick = () => {
    if (state === 'idle') {
      start()
    } else if (state === 'speaking') {
      interrupt()
    }
  }

  const handleSend = useCallback(
    async (content: string) => {
      // A call holds the conversation: end it so the typed turn is not lost.
      if (callActive) stop()
      await chat.sendMessage(content)
    },
    [callActive, stop, chat],
  )

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 min-w-0 overflow-y-auto">
        <div className="flex flex-col items-center justify-center min-h-full px-4 py-8 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
            className="flex flex-col items-center gap-8 w-full"
          >
            <VoiceOrb state={state} volume={volume} onClick={handleOrbClick} />

            <StatusChips chips={statusChips} />

            <VoiceIndicators micPermission={micPermission} connectionQuality={connectionQuality} />

            <LiveTranscript userTranscript={userTranscript} assistantTranscript={assistantTranscript} />

            <VoiceControls
              state={state}
              isMuted={isMuted}
              isPaused={isPaused}
              onToggleMute={toggleMute}
              onTogglePause={togglePause}
              onStop={stop}
              isChatOpen={isChatOpen}
              onToggleChat={() => setIsChatOpen((open) => !open)}
            />
          </motion.div>
        </div>
      </div>

      <ChatPanel
        open={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        messages={chat.messages}
        learning={chat.learning}
        liveTurns={showLive ? liveTurns : []}
        isSending={chat.isSending}
        isLoadingHistory={chat.isLoadingHistory}
        callActive={callActive}
        onSend={handleSend}
        onReset={chat.resetConversation}
      />
    </div>
  )
}
