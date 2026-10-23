import { useState, useRef, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { createWebSocket } from '@/shared/lib/api'
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
  
  const wsRef = useRef<WebSocket | null>(null)
  const threadId = useRef(`thread-${Date.now()}`)
  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const isMutedRef = useRef(false)
  const isPausedRef = useRef(false)

  const floatTo16BitPCM = (input: Float32Array): ArrayBuffer => {
    const buffer = new ArrayBuffer(input.length * 2)
    const view = new DataView(buffer)
    for (let i = 0; i < input.length; i++) {
      let s = Math.max(-1, Math.min(1, input[i]))
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true)
    }
    return buffer
  }

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
          sampleRate: 16000, 
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        } 
      })
      streamRef.current = stream
      setMicPermission('granted')
      
      audioContextRef.current = new AudioContext({ sampleRate: 16000 })
      const analyser = audioContextRef.current.createAnalyser()
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream)
      sourceRef.current.connect(analyser)
      analyser.fftSize = 256
      
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const updateVolume = () => {
        if (analyser && !isPausedRef.current) {
          analyser.getByteFrequencyData(dataArray)
          const average = dataArray.reduce((a, b) => a + b) / dataArray.length
          setVolume(average / 255)
        }
        requestAnimationFrame(updateVolume)
      }
      updateVolume()
      
      const ws = createWebSocket(`/api/v1/voice/${threadId.current}`)
      wsRef.current = ws
      ws.binaryType = 'arraybuffer'
      
      ws.onopen = () => {
        console.log('WS connected')
        setState('listening')
        setStatusChips(['Escuchando...'])
        setConnectionQuality('good')
        setUserTranscript('')
        setAssistantTranscript('')
        
        ws.send(JSON.stringify({ type: 'session.start', sampleRate: 16000 }))
        
        const source = sourceRef.current!
        const processor = audioContextRef.current!.createScriptProcessor(4096, 1, 1)
        processorRef.current = processor
        
        processor.onaudioprocess = (e) => {
          if (ws.readyState === WebSocket.OPEN && !isMutedRef.current && !isPausedRef.current) {
            const inputData = e.inputBuffer.getChannelData(0)
            const pcmData = floatTo16BitPCM(inputData)
            ws.send(pcmData)
          }
        }
        
        source.connect(processor)
        processor.connect(audioContextRef.current!.destination)
      }
      
      let currentAudioContext: AudioContext | null = null
      let audioQueue: ArrayBuffer[] = []
      let isPlaying = false

      const playNextAudio = async () => {
        if (isPlaying || audioQueue.length === 0) return
        isPlaying = true
        const buffer = audioQueue.shift()!
        try {
          if (!currentAudioContext || currentAudioContext.state === 'closed') {
            currentAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 })
          }
          if (currentAudioContext.state === 'suspended') {
            await currentAudioContext.resume()
          }
          const audioBuffer = await currentAudioContext.decodeAudioData(buffer.slice(0))
          const source = currentAudioContext.createBufferSource()
          source.buffer = audioBuffer
          source.connect(currentAudioContext.destination)
          source.onended = () => {
            isPlaying = false
            playNextAudio()
          }
          source.start()
        } catch (e) {
          console.error('Error playing audio:', e)
          isPlaying = false
          playNextAudio()
        }
      }

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            const data = JSON.parse(event.data)
            console.log('WS:', data.type, data.name)
            if (data.type === 'CUSTOM') {
              if (data.name === 'voice.session_end' || data.name === 'voice_session_end') {
                setState('idle')
                setStatusChips([])
              } else if (data.name === 'voice.transcript') {
                if (data.value?.text) {
                  setUserTranscript(data.value.utterance || data.value.text)
                }
              } else if (data.name === 'voice.listening') {
                if (data.value?.active) {
                  setState('listening')
                  setStatusChips(['Escuchando...'])
                } else {
                  setState('processing')
                  setStatusChips(['Procesando...'])
                }
              } else if (data.name === 'voice.interrupted') {
                setState('interrupted')
                setStatusChips(['Interrumpido'])
              } else if (data.name === 'voice.audio_start') {
                setState('speaking')
                setStatusChips(['Hablando...'])
                setAssistantTranscript('')
                audioQueue = []
                isPlaying = false
              } else if (data.name === 'voice.audio_end') {
                setState('listening')
                setStatusChips(['Escuchando...'])
              }
            } else if (data.type === 'RUN_STARTED') {
              setState('processing')
              setStatusChips(['Procesando...'])
            } else if (data.type === 'TEXT_MESSAGE_START') {
              setState('speaking')
              setStatusChips(['Hablando...'])
              setAssistantTranscript('')
            } else if (data.type === 'TEXT_MESSAGE_CONTENT') {
              setAssistantTranscript((prev) => prev + (data.delta || ''))
            } else if (data.type === 'TEXT_MESSAGE_END') {
              // Keep speaking until audio ends
            } else if (data.type === 'RUN_ERROR') {
              console.error('Run error:', data.message)
              setState('listening')
              setStatusChips(['Error'])
            }
          } catch (e) {
            console.error('Error parsing:', e)
          }
        } else if (event.data instanceof ArrayBuffer) {
          audioQueue.push(event.data)
          playNextAudio()
        }
      }
      
      ws.onerror = (e) => {
        console.error('WS error:', e)
        setConnectionQuality('weak')
      }
      
      ws.onclose = (e) => {
        console.log('WS closed:', e.code)
        setState('idle')
        setStatusChips([])
      }
    } catch (error) {
      console.error('Error starting:', error)
      setMicPermission('denied')
    }
  }, [])

  const stop = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'session.stop' }))
      } catch {}
      wsRef.current.close()
    }
    wsRef.current = null
    setState('idle')
    setStatusChips([])
    setUserTranscript('')
    setAssistantTranscript('')
    setVolume(0)
  }, [])

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      isMutedRef.current = !prev
      return !prev
    })
  }, [])

  const togglePause = useCallback(() => {
    setIsPaused((prev) => {
      isPausedRef.current = !prev
      return !prev
    })
  }, [])

  const interrupt = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }))
    }
    setState('interrupted')
    setStatusChips(['Interrumpido'])
  }, [])

  const switchToChat = useCallback(() => {
    stop()
    navigate({ to: '/chat' })
  }, [navigate, stop])

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
