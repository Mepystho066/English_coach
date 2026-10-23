import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { PipecatClient, TransportState } from '@pipecat-ai/client-js'
import { WebSocketTransport } from '@pipecat-ai/websocket-transport'
import { env } from '@/core/config/env'
import { VoiceSessionState } from '@/shared/types'

export interface IVoiceSession {
  state: VoiceSessionState
  isMuted: boolean
  isPaused: boolean
  volume: number
  userTranscript: string
  assistantTranscript: string
  statusChips: string[]
  micPermission: 'granted' | 'denied' | 'prompt'
  connectionQuality: 'good' | 'weak' | 'reconnecting'
  start: () => void
  stop: () => void
  toggleMute: () => void
  togglePause: () => void
  interrupt: () => void
  switchToChat: () => void
}

/** Sample rates the backend pipeline is configured with. */
const INPUT_SAMPLE_RATE = 16_000
const OUTPUT_SAMPLE_RATE = 24_000

function voiceUrl(threadId: string): string {
  const base = env.API_URL.replace(/^http/, 'ws')
  return `${base}/api/v1/voice/${threadId}`
}

export function useVoiceSession(): IVoiceSession {
  const navigate = useNavigate()
  const [state, setState] = useState<VoiceSessionState>('idle')
  const [isMuted, setIsMuted] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [volume, setVolume] = useState(0)
  const [userTranscript, setUserTranscript] = useState('')
  const [assistantTranscript, setAssistantTranscript] = useState('')
  const [statusChips, setStatusChips] = useState<string[]>([])
  const [micPermission, setMicPermission] = useState<'granted' | 'denied' | 'prompt'>('prompt')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'weak' | 'reconnecting'>('good')

  const clientRef = useRef<PipecatClient | null>(null)
  const threadIdRef = useRef(`thread-${Date.now()}`)
  const mutedRef = useRef(false)
  const pausedRef = useRef(false)

  const makeClient = useCallback(() => {
    const transport = new WebSocketTransport({
      wsUrl: voiceUrl(threadIdRef.current),
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
          if (data?.text) setUserTranscript(data.text)
        },
        onBotLlmStarted: () => {
          setAssistantTranscript('')
        },
        onBotLlmText: (data) => {
          if (data?.text) {
            setAssistantTranscript((previous) => previous + data.text)
          }
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
    setStatusChips(['Conectando...'])

    try {
      await client.connect()
    } catch (error) {
      console.error('Error starting voice session:', error)
      setMicPermission('denied')
      setConnectionQuality('weak')
      setStatusChips(['No se pudo conectar'])
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

  const switchToChat = useCallback(() => {
    stop()
    navigate({ to: '/chat' })
  }, [navigate, stop])

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
    statusChips,
    micPermission,
    connectionQuality,
    start,
    stop,
    toggleMute,
    togglePause,
    interrupt,
    switchToChat,
  }
}
