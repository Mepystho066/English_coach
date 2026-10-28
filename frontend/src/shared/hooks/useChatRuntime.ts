import { useState, useCallback, useEffect, useRef } from 'react'
import { ChatMessage } from '@/shared/types'
import { EMPTY_LEARNING, LearningState, toLearningState } from '@/shared/types/learning'
import { env } from '@/core/config/env'
import { getThreadId, resetThreadId } from '@/shared/lib/thread'

export interface IChatRuntime {
  messages: ChatMessage[]
  learning: LearningState
  isSending: boolean
  isLoadingHistory: boolean
  sendMessage: (content: string) => Promise<void>
  resetConversation: () => Promise<void>
  refresh: () => Promise<void>
  /** Replace the learning state (used for updates that arrive by voice). */
  applyLearning: (state: LearningState) => void
}

interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
}

// The analysis runs on the server a few seconds after the reply.
const POLL_INTERVAL_MS = 3000
// Local reasoning models can take a while, and the user can also reload the
// panel to pick the state up once it lands.
const POLL_MAX_TRIES = 30

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

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
  const [learning, setLearning] = useState<LearningState>(EMPTY_LEARNING)
  const [isSending, setIsSending] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)

  // True while a reply is streaming: history reloads must not overwrite it.
  const streamingRef = useRef(false)
  const learningRef = useRef<LearningState>(EMPTY_LEARNING)
  // Bumped when the conversation changes, to stop a poll that is still running.
  const pollGeneration = useRef(0)

  const applyLearning = useCallback((state: LearningState) => {
    learningRef.current = state
    setLearning(state)
  }, [])

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

  const loadLearning = useCallback(async (): Promise<LearningState | null> => {
    try {
      const response = await fetch(
        `${env.API_URL}/api/v1/threads/${encodeURIComponent(threadId)}/state`,
      )
      if (!response.ok) throw new Error(`State error: ${response.status}`)
      return toLearningState(await response.json())
    } catch (error) {
      console.error('Error loading learning state:', error)
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
    pollGeneration.current += 1
    setIsLoadingHistory(true)
    applyLearning(EMPTY_LEARNING)

    Promise.all([loadHistory(), loadLearning()]).then(([stored, state]) => {
      if (cancelled) return
      applyHistory(stored)
      if (state) applyLearning(state)
      setIsLoadingHistory(false)
    })
    return () => {
      cancelled = true
    }
  }, [loadHistory, loadLearning, applyHistory, applyLearning])

  /** Reload the stored conversation (e.g. after a voice call ends). */
  const refresh = useCallback(async () => {
    const [stored, state] = await Promise.all([loadHistory(), loadLearning()])
    if (state) applyLearning(state)
    // Never replace the list while a reply is streaming in.
    if (stored && !streamingRef.current) applyHistory(stored)
  }, [loadHistory, loadLearning, applyHistory, applyLearning])

  /** Wait for the server to finish analyzing the message just sent. */
  const waitForAnalysis = useCallback(
    async (turnsBefore: number) => {
      const generation = pollGeneration.current
      for (let attempt = 0; attempt < POLL_MAX_TRIES; attempt += 1) {
        await sleep(POLL_INTERVAL_MS)
        if (generation !== pollGeneration.current) return
        if (learningRef.current.turns > turnsBefore) return
        const state = await loadLearning()
        if (generation !== pollGeneration.current) return
        if (state && state.turns > turnsBefore) {
          applyLearning(state)
          return
        }
        if (state && !state.enabled) return
      }
    },
    [loadLearning, applyLearning],
  )

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isSending) return

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMessage])
    streamingRef.current = true
    setIsSending(true)

    const turnsBefore = learningRef.current.turns
    let gotSnapshot = false

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
          if (data.type === 'TEXT_MESSAGE_START') {
            assistantContent = ''
          } else if (data.type === 'TEXT_MESSAGE_CONTENT') {
            assistantContent += data.delta
          } else if (data.type === 'TEXT_MESSAGE_END') {
            // Models often open with an empty message before calling a tool.
            if (assistantContent.trim()) {
              const assistantMessage: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: assistantContent,
                timestamp: Date.now(),
              }
              setMessages((prev) => [...prev, assistantMessage])
              // The reply is in; what is left on the stream is bookkeeping.
              setIsSending(false)
            }
            assistantContent = ''
          } else if (data.type === 'STATE_SNAPSHOT') {
            gotSnapshot = true
            applyLearning(toLearningState(data.snapshot))
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
      streamingRef.current = false
      setIsSending(false)
    }

    // The analysis usually finishes after the stream closes: poll for it.
    if (!gotSnapshot) await waitForAnalysis(turnsBefore)
  }, [isSending, threadId, applyLearning, waitForAnalysis])

  const resetConversation = useCallback(async () => {
    pollGeneration.current += 1
    try {
      await fetch(`${env.API_URL}/api/v1/threads/${encodeURIComponent(threadId)}`, {
        method: 'DELETE',
      })
    } catch (error) {
      console.error('Error clearing conversation:', error)
    }
    applyLearning(EMPTY_LEARNING)
    setThreadId(resetThreadId())
  }, [threadId, applyLearning])

  return {
    messages,
    learning,
    isSending,
    isLoadingHistory,
    sendMessage,
    resetConversation,
    refresh,
    applyLearning,
  }
}
