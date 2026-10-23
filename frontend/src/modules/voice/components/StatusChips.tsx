import { motion, AnimatePresence } from 'motion/react'
import { Loader2 } from 'lucide-react'

interface StatusChipsProps {
  chips: string[]
}

export function StatusChips({ chips }: StatusChipsProps) {
  if (chips.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 justify-center px-4">
      <AnimatePresence>
        {chips.map((chip, index) => (
          <motion.div
            key={chip + index}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-secondary/80 backdrop-blur-sm text-sm"
            role="status"
            aria-label={chip}
          >
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>{chip}</span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
