import { useState, useCallback } from 'react'
import { ChatMessage } from '@/shared/types'
import { env } from '@/core/config/env'

export interface IChatRuntime {
  messages: ChatMessage[]
  isSending: boolean
  sendMessage: (content: string) => Promise<void>
}

export function useChatRuntime(threadId: string = 'default'): IChatRuntime {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: '¡Hola! Soy tu coach de inglés. ¿De qué quieres hablar hoy?',
      timestamp: Date.now() - 3600000,
    },
  ])
  const [isSending, setIsSending] = useState(false)

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isSending) return

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMessage])
    setIsSending(true)

    try {
      const response = await fetch(`${env.API_URL}/api/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          threadId,
          runId: `run-${Date.now()}`,
          messages: [
            {
              id: userMessage.id,
              role: 'user',
              content: content,
            },
          ],
          tools: [],
          context: [],
          forwardedProps: {},
        }),
      })

      if (!response.ok) throw new Error('Failed to send message')

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'TEXT_MESSAGE_CONTENT') {
                  assistantContent += data.delta
                } else if (data.type === 'TEXT_MESSAGE_END') {
                  const assistantMessage: ChatMessage = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: assistantContent,
                    timestamp: Date.now(),
                  }
                  setMessages((prev) => [...prev, assistantMessage])
                  assistantContent = ''
                }
              } catch (e) {
                // Skip invalid JSON
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error sending message:', error)
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo.',
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsSending(false)
    }
  }, [messages, isSending, threadId])

  return {
    messages,
    isSending,
    sendMessage,
  }
}
