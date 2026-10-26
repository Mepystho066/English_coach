import { useCallback, useEffect, useRef, useState } from 'react'
import { PipecatClient, TransportState } from '@pipecat-ai/client-js'
import { WebSocketTransport } from '@pipecat-ai/websocket-transport'
import { env } from '@/core/config/env'
import { VoiceSessionState } from '@/shared/types'
import { getThreadId } from '@/shared/lib/thread'

export interface LiveTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
}

export interface IVoiceSession {
  state: VoiceSessionState
  isMuted: boolean
  isPaused: boolean
  volume: number
  userTranscript: string
  assistantTranscript: string
  liveTurns: LiveTurn[]
  statusChips: string[]
  micPermission: 'granted' | 'denied' | 'prompt'
  connectionQuality: 'good' | 'weak' | 'reconnecting'
  start: () => void
  stop: () => void
  toggleMute: () => void
  togglePause: () => void
  interrupt: () => void
}

/** Sample rates the backend pipeline is configured with. */
const INPUT_SAMPLE_RATE = 16_000
const OUTPUT_SAMPLE_RATE = 24_000

function voiceUrl(threadId: string): string {
  const base = env.API_URL
    ? env.API_URL.replace(/^http/, 'ws')
    : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  return `${base}/api/v1/voice/${threadId}`
}

function isMicError(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name
  return (
    name === 'NotAllowedError' ||
    name === 'NotFoundError' ||
    name === 'SecurityError' ||
    !window.isSecureContext
  )
}

export function useVoiceSession(): IVoiceSession {
  const [state, setState] = useState<VoiceSessionState>('idle')
  const [isMuted, setIsMuted] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [volume, setVolume] = useState(0)
  const [userTranscript, setUserTranscript] = useState('')
  const [assistantTranscript, setAssistantTranscript] = useState('')
  const [liveTurns, setLiveTurns] = useState<LiveTurn[]>([])
  const [statusChips, setStatusChips] = useState<string[]>([])
  const [micPermission, setMicPermission] = useState<'granted' | 'denied' | 'prompt'>('prompt')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'weak' | 'reconnecting'>('good')

  const clientRef = useRef<PipecatClient | null>(null)
  const mutedRef = useRef(false)
  const pausedRef = useRef(false)

  const makeClient = useCallback(() => {
    const transport = new WebSocketTransport({
      wsUrl: voiceUrl(getThreadId()),
      recorderSampleRate: INPUT_SAMPLE_RATE,
      playerSampleRate: OUTPUT_SAMPLE_RATE,
    })

    return new PipecatClient({
      transport,
      enableMic: true,
      callbacks: {
        onTransportStateChanged: (transportState: TransportState) => {
          if (transportState === 'error' || transportState === 'disconnected') {
            setConnectionQuality(transportState === 'error' ? 'weak' : 'good')
          } else if (
            transportState === 'connecting' ||
            transportState === 'authenticating' ||
            transportState === 'initializing'
          ) {
            setConnectionQuality('reconnecting')
          } else if (transportState === 'ready' || transportState === 'connected') {
            setConnectionQuality('good')
          }
        },
        onBotReady: () => {
          setMicPermission('granted')
          setConnectionQuality('good')
          setState('listening')
          setStatusChips(['Escuchando...'])
          // Apply a mute/pause chosen before the session finished connecting.
          clientRef.current?.enableMic(
            !mutedRef.current && !pausedRef.current,
          )
        },
        onUserStartedSpeaking: () => {
          setState('listening')
          setStatusChips(['Escuchando...'])
        },
        onUserStoppedSpeaking: () => {
          setState('processing')
          setStatusChips(['Procesando...'])
        },
        onUserTranscript: (data) => {
          if (!data?.text) return
          setUserTranscript(data.text)
          if (data.final) {
            const text = data.text
            setLiveTurns((previous) => [
              ...previous,
              { id: `u-${Date.now()}-${previous.length}`, role: 'user', text },
            ])
          }
        },
        onBotLlmStarted: () => {
          setAssistantTranscript('')
          setLiveTurns((previous) => [
            ...previous,
            { id: `a-${Date.now()}-${previous.length}`, role: 'assistant', text: '' },
          ])
        },
        onBotLlmText: (data) => {
          if (!data?.text) return
          const text = data.text
          setAssistantTranscript((previous) => previous + text)
          setLiveTurns((previous) => {
            const last = previous[previous.length - 1]
            if (!last || last.role !== 'assistant') return previous
            return [...previous.slice(0, -1), { ...last, text: last.text + text }]
          })
        },
        onBotStartedSpeaking: () => {
          setState('speaking')
          setStatusChips(['Hablando...'])
        },
        onBotStoppedSpeaking: () => {
          setState('listening')
          setStatusChips(['Escuchando...'])
        },
        onLocalAudioLevel: (level) => {
          // The transport reports 0..1; smooth it a little for the orb.
          setVolume((previous) => Math.max(0, Math.min(1, previous * 0.6 + level * 0.4)))
        },
        onDeviceError: () => {
          setMicPermission('denied')
        },
        onError: (message) => {
          console.error('Voice session error:', message)
          setConnectionQuality('weak')
          setStatusChips(['Error de conexión'])
        },
      },
    })
  }, [])

  const start = useCallback(async () => {
    if (clientRef.current) return

    const client = makeClient()
    clientRef.current = client
    setUserTranscript('')
    setAssistantTranscript('')
    setLiveTurns([])
    setStatusChips(['Conectando...'])

    try {
      await client.connect()
    } catch (error) {
      console.error('Error starting voice session:', error)
      const micProblem = isMicError(error)
      if (micProblem) setMicPermission('denied')
      setConnectionQuality('weak')
      setStatusChips([micProblem ? 'Micrófono no disponible' : 'No se pudo conectar al servidor'])
      setState('idle')
      clientRef.current = null
      try {
        await client.disconnect()
      } catch {
        // Already disconnected.
      }
    }
  }, [makeClient])

  const stop = useCallback(() => {
    const client = clientRef.current
    clientRef.current = null
    if (client) {
      client.disconnect().catch((error) => {
        console.error('Error closing voice session:', error)
      })
    }
    setState('idle')
    setStatusChips([])
    setUserTranscript('')
    setAssistantTranscript('')
    setVolume(0)
  }, [])

  const toggleMute = useCallback(() => {
    setIsMuted((previous) => {
      const next = !previous
      mutedRef.current = next
      clientRef.current?.enableMic(!next && !pausedRef.current)
      return next
    })
  }, [])

  const togglePause = useCallback(() => {
    setIsPaused((previous) => {
      const next = !previous
      pausedRef.current = next
      clientRef.current?.enableMic(!next && !mutedRef.current)
      return next
    })
  }, [])

  const interrupt = useCallback(() => {
    // Barge-in by voice is handled by the server's VAD; this is the button.
    clientRef.current?.sendClientMessage('interrupt')
    setState('interrupted')
    setStatusChips(['Interrumpido'])
  }, [])

  useEffect(() => {
    return () => {
      const client = clientRef.current
      clientRef.current = null
      if (client) {
        client.disconnect().catch(() => {
          // Nothing to clean up if the socket is already gone.
        })
      }
    }
  }, [])

  return {
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
  }
}
