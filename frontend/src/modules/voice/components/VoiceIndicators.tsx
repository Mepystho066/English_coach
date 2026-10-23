import { WifiOff, Mic, AlertCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

interface VoiceIndicatorsProps {
  micPermission: 'granted' | 'denied' | 'prompt'
  connectionQuality: 'good' | 'weak' | 'reconnecting'
}

export function VoiceIndicators({ micPermission, connectionQuality }: VoiceIndicatorsProps) {
  return (
    <div className="flex flex-wrap gap-2 justify-center px-4">
      <AnimatePresence>
        {micPermission === 'denied' && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-destructive/10 text-destructive text-sm"
            role="alert"
            aria-label="Permiso de micrófono denegado"
          >
            <Mic className="h-3 w-3" />
            <span>Permiso de micrófono denegado</span>
          </motion.div>
        )}
        {micPermission === 'prompt' && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 text-sm"
            role="status"
            aria-label="Se necesita permiso de micrófono"
          >
            <AlertCircle className="h-3 w-3" />
            <span>Se necesita permiso de micrófono</span>
          </motion.div>
        )}
        {connectionQuality === 'weak' && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 text-sm"
            role="status"
            aria-label="Conexión débil"
          >
            <WifiOff className="h-3 w-3" />
            <span>Conexión débil</span>
          </motion.div>
        )}
        {connectionQuality === 'reconnecting' && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 text-sm"
            role="status"
            aria-label="Reconectando"
          >
            <WifiOff className="h-3 w-3" />
            <span>Reconectando...</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
