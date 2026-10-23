import { VoiceOrb } from './components/VoiceOrb'
import { LiveTranscript } from './components/LiveTranscript'
import { VoiceControls } from './components/VoiceControls'
import { StatusChips } from './components/StatusChips'
import { VoiceIndicators } from './components/VoiceIndicators'
import { motion } from 'motion/react'
import { useVoiceSession } from '@/shared/hooks/useVoiceSession'

export function VoicePage() {
  const {
    state,
    isMuted,
    isPaused,
    volume,
    userTranscript,
    assistantTranscript,
    statusChips,
    micPermission,
    connectionQuality,
    start,
    stop,
    toggleMute,
    togglePause,
    interrupt,
    switchToChat,
  } = useVoiceSession()

  const handleOrbClick = () => {
    if (state === 'idle') {
      start()
    } else if (state === 'speaking') {
      interrupt()
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] md:min-h-[calc(100vh-4rem)] px-4 py-8 gap-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
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
          onSwitchToChat={switchToChat}
        />
      </motion.div>
    </div>
  )
}
