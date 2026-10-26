import { useState, useCallback, useEffect, useRef } from 'react'
import { ChatMessage } from '@/shared/types'
import { env } from '@/core/config/env'
import { getThreadId, resetThreadId } from '@/shared/lib/thread'

export interface IChatRuntime {
  messages: ChatMessage[]
  isSending: boolean
  isLoadingHistory: boolean
  sendMessage: (content: string) => Promise<void>
  resetConversation: () => Promise<void>
  refresh: () => Promise<void>
}

interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
}

function greeting(): ChatMessage {
  return {
    id: 'greeting',
    role: 'assistant',
    content: '¡Hola! Soy tu coach de inglés. ¿De qué quieres hablar hoy?',
    timestamp: Date.now(),
  }
}

export function useChatRuntime(): IChatRuntime {
  const [threadId, setThreadId] = useState(getThreadId)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)

  const isSendingRef = useRef(false)

  const loadHistory = useCallback(async (): Promise<StoredMessage[] | null> => {
    try {
      const response = await fetch(
        `${env.API_URL}/api/v1/threads/${encodeURIComponent(threadId)}/messages`,
      )
      if (!response.ok) throw new Error(`History error: ${response.status}`)
      const body = (await response.json()) as { messages: StoredMessage[] }
      return body.messages
    } catch (error) {
      console.error('Error loading history:', error)
      return null
    }
  }, [threadId])

  const applyHistory = useCallback((stored: StoredMessage[] | null) => {
    const now = Date.now()
    setMessages(
      stored && stored.length > 0
        ? stored.map((message, index) => ({
            id: `history-${index}`,
            role: message.role,
            content: message.content,
            timestamp: now,
          }))
        : [greeting()],
    )
  }, [])

  useEffect(() => {
    let cancelled = false
    setIsLoadingHistory(true)
    loadHistory().then((stored) => {
      if (cancelled) return
      applyHistory(stored)
      setIsLoadingHistory(false)
    })
    return () => {
      cancelled = true
    }
  }, [loadHistory, applyHistory])

  /** Reload the stored conversation (e.g. after a voice call ends). */
  const refresh = useCallback(async () => {
    const stored = await loadHistory()
    // Never replace the list while a reply is streaming in.
    if (stored && !isSendingRef.current) applyHistory(stored)
  }, [loadHistory, applyHistory])

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isSending) return

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMessage])
    isSendingRef.current = true
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
      let buffer = ''

      const handleLine = (line: string) => {
        if (!line.startsWith('data: ')) return
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
        } catch {
          // Skip invalid JSON
        }
      }

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          // A `data:` line can be split across reads: keep the unfinished tail.
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          lines.forEach(handleLine)
        }
        if (buffer) handleLine(buffer)
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
      isSendingRef.current = false
      setIsSending(false)
    }
  }, [isSending, threadId])

  const resetConversation = useCallback(async () => {
    try {
      await fetch(`${env.API_URL}/api/v1/threads/${encodeURIComponent(threadId)}`, {
        method: 'DELETE',
      })
    } catch (error) {
      console.error('Error clearing conversation:', error)
    }
    setThreadId(resetThreadId())
  }, [threadId])

  return {
    messages,
    isSending,
    isLoadingHistory,
    sendMessage,
    resetConversation,
    refresh,
  }
}
