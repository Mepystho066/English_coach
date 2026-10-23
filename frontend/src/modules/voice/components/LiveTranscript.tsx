import { motion, AnimatePresence } from 'motion/react'

interface LiveTranscriptProps {
  userTranscript: string
  assistantTranscript: string
}

export function LiveTranscript({ userTranscript, assistantTranscript }: LiveTranscriptProps) {
  return (
    <div className="w-full max-w-2xl px-4 space-y-6" aria-live="polite" aria-label="Transcripción en vivo">
      <AnimatePresence mode="wait">
        {userTranscript && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="flex flex-col items-end"
          >
            <div className="inline-block max-w-[85%] px-5 py-3 rounded-3xl rounded-br-md bg-gradient-to-br from-primary to-primary/90 text-primary-foreground shadow-lg shadow-primary/20">
              <p className="text-sm md:text-base leading-relaxed">{userTranscript}</p>
            </div>
            <p className="text-xs text-muted-foreground mt-2 mr-1">Tú</p>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {assistantTranscript && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
            className="flex flex-col items-start"
          >
            <p className="text-xs text-muted-foreground mb-2 ml-1">Asistente</p>
            <div className="inline-block max-w-[85%] px-5 py-3 rounded-3xl rounded-bl-md bg-card border border-border/50 backdrop-blur-sm shadow-lg">
              <p className="text-sm md:text-base leading-relaxed text-foreground">
                {assistantTranscript}
                <motion.span
                  animate={{ opacity: [1, 0, 1] }}
                  transition={{ duration: 0.8, repeat: Infinity }}
                  className="inline-block ml-1 text-primary"
                >
                  |
                </motion.span>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
