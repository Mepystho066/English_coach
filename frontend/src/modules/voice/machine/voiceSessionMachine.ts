import { createMachine, assign } from 'xstate'

export interface VoiceSessionContext {
  volume: number
  isMuted: boolean
  isPaused: boolean
  userTranscript: string
  assistantTranscript: string
  statusChips: string[]
  micPermission: 'granted' | 'denied' | 'prompt'
  connectionQuality: 'good' | 'weak' | 'reconnecting'
}

export type VoiceSessionEvent =
  | { type: 'START' }
  | { type: 'STOP' }
  | { type: 'MIC_VOLUME'; volume: number }
  | { type: 'USER_SPEECH_START' }
  | { type: 'USER_SPEECH_END'; transcript: string }
  | { type: 'ASSISTANT_START' }
  | { type: 'ASSISTANT_DELTA'; delta: string }
  | { type: 'ASSISTANT_END' }
  | { type: 'INTERRUPT' }
  | { type: 'TOGGLE_MUTE' }
  | { type: 'TOGGLE_PAUSE' }
  | { type: 'SWITCH_TO_CHAT' }

export const voiceSessionMachine = createMachine({
  id: 'voiceSession',
  types: {} as {
    context: VoiceSessionContext
    events: VoiceSessionEvent
  },
  initial: 'idle',
  context: {
    volume: 0,
    isMuted: false,
    isPaused: false,
    userTranscript: '',
    assistantTranscript: '',
    statusChips: [],
    micPermission: 'prompt',
    connectionQuality: 'good',
  },
  states: {
    idle: {
      on: {
        START: {
          target: 'listening',
          actions: assign({
            statusChips: () => ['Escuchando...'],
            userTranscript: () => '',
            assistantTranscript: () => '',
          }),
        },
      },
    },
    listening: {
      on: {
        MIC_VOLUME: {
          actions: assign({
            volume: ({ event }) => event.volume,
          }),
        },
        USER_SPEECH_END: {
          target: 'processing',
          actions: assign({
            userTranscript: ({ event }) => event.transcript,
            statusChips: () => ['Procesando...'],
          }),
        },
        INTERRUPT: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
            volume: () => 0,
          }),
        },
        TOGGLE_MUTE: {
          actions: assign({
            isMuted: ({ context }) => !context.isMuted,
          }),
        },
        STOP: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
            volume: () => 0,
          }),
        },
      },
    },
    processing: {
      on: {
        ASSISTANT_START: {
          target: 'speaking',
          actions: assign({
            statusChips: () => ['Consultando...'],
            assistantTranscript: () => '',
          }),
        },
        INTERRUPT: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
          }),
        },
        STOP: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
          }),
        },
      },
    },
    speaking: {
      on: {
        ASSISTANT_DELTA: {
          actions: assign({
            assistantTranscript: ({ context, event }) => context.assistantTranscript + event.delta,
            statusChips: () => ['Hablando...'],
          }),
        },
        ASSISTANT_END: {
          target: 'listening',
          actions: assign({
            statusChips: () => ['Escuchando...'],
          }),
        },
        INTERRUPT: {
          target: 'interrupted',
          actions: assign({
            statusChips: () => ['Interrumpido'],
          }),
        },
        STOP: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
          }),
        },
      },
    },
    interrupted: {
      on: {
        START: {
          target: 'listening',
          actions: assign({
            statusChips: () => ['Escuchando...'],
          }),
        },
        STOP: {
          target: 'idle',
          actions: assign({
            statusChips: () => [],
          }),
        },
      },
    },
  },
})
