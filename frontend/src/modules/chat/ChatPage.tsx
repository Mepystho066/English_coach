import { useState } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Textarea } from '@/shared/ui/textarea'
import { ScrollArea } from '@/shared/ui/scroll-area'
import { motion } from 'motion/react'
import { useChatRuntime } from '@/shared/hooks/useChatRuntime'

export function ChatPage() {
  const { messages, isSending, sendMessage } = useChatRuntime()
  const [input, setInput] = useState('')

  const handleSend = async () => {
    if (!input.trim() || isSending) return
    await sendMessage(input)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)] max-w-4xl mx-auto">
      <ScrollArea className="flex-1 px-4 py-6">
        <div className="space-y-4">
          {messages.map((message, index) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-4 py-2 rounded-3xl ${
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary'
                }`}
              >
                <p className="text-sm md:text-base whitespace-pre-wrap">{message.content}</p>
              </div>
            </motion.div>
          ))}
          {isSending && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start"
            >
              <div className="max-w-[80%] px-4 py-2 rounded-3xl bg-secondary">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce"></span>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t p-4">
        <div className="flex gap-2 items-end">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribe un mensaje..."
            className="min-h-[60px] max-h-[200px] resize-none rounded-2xl"
            rows={1}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            size="icon"
            className="rounded-full h-12 w-12 flex-shrink-0"
            aria-label="Enviar mensaje"
          >
            <Send className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  )
}
