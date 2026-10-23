import { motion } from 'motion/react'
import { VoiceSessionState } from '@/shared/types'
import { cn } from '@/shared/lib/utils'

interface VoiceOrbProps {
  state: VoiceSessionState
  volume?: number
  onClick?: () => void
}

export function VoiceOrb({ state, volume = 0, onClick }: VoiceOrbProps) {
  const getScale = () => {
    if (state === 'listening') {
      return 1 + volume * 0.3
    }
    if (state === 'speaking') {
      return 1.1
    }
    if (state === 'processing') {
      return 1.05
    }
    return 1
  }

  const getGlowColor = () => {
    switch (state) {
      case 'listening':
        return 'from-violet-500/60 to-purple-600/60'
      case 'speaking':
        return 'from-fuchsia-500/60 to-pink-600/60'
      case 'processing':
        return 'from-blue-500/60 to-cyan-600/60'
      case 'interrupted':
        return 'from-orange-500/60 to-red-600/60'
      default:
        return 'from-violet-400/40 to-purple-500/40'
    }
  }

  return (
    <motion.button
      onClick={onClick}
      className={cn(
        'relative w-48 h-48 md:w-64 md:h-64 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-4 focus-visible:ring-offset-background',
        'flex items-center justify-center cursor-pointer shadow-2xl'
      )}
      animate={{
        scale: getScale(),
      }}
      whileHover={{ scale: getScale() * 1.05 }}
      whileTap={{ scale: getScale() * 0.95 }}
      transition={{
        type: 'spring',
        stiffness: 400,
        damping: 25,
      }}
      aria-label={`Orb - Estado: ${state}`}
    >
      {/* Outer glow */}
      <motion.div
        className={cn(
          'absolute inset-0 rounded-full bg-gradient-to-br blur-3xl',
          getGlowColor()
        )}
        animate={{
          opacity: state === 'idle' ? 0.4 : 0.7,
          scale: state === 'processing' ? [1, 1.15, 1] : state === 'speaking' ? [1, 1.08, 1] : 1,
        }}
        transition={{
          duration: state === 'processing' ? 1.8 : state === 'speaking' ? 1.2 : 2,
          repeat: (state === 'processing' || state === 'speaking') ? Infinity : 0,
          ease: 'easeInOut',
        }}
      />
      
      {/* Middle ring */}
      <motion.div
        className={cn(
          'absolute inset-3 rounded-full bg-gradient-to-br backdrop-blur-md border border-white/10',
          getGlowColor()
        )}
        animate={{
          scale: state === 'listening' ? [1, 1.04, 1] : 1,
          rotate: state === 'speaking' ? 360 : 0,
        }}
        transition={{
          scale: {
            duration: 1.5,
            repeat: state === 'listening' ? Infinity : 0,
            ease: 'easeInOut',
          },
          rotate: {
            duration: 8,
            repeat: state === 'speaking' ? Infinity : 0,
            ease: 'linear',
          }
        }}
      />
      
      {/* Inner orb */}
      <div className="absolute inset-6 rounded-full bg-gradient-to-br from-primary via-purple-500 to-violet-600 backdrop-blur-xl shadow-inner" />
      
      {/* Core pulse */}
      {(state === 'speaking' || state === 'processing') && (
        <motion.div
          className="absolute inset-10 rounded-full bg-white/30"
          animate={{
            scale: [1, 1.3, 1],
            opacity: [0.6, 0.1, 0.6],
          }}
          transition={{
            duration: state === 'processing' ? 1.8 : 1.4,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      )}
    </motion.button>
  )
}
