export type CorrectionCategory = 'grammar' | 'vocabulary' | 'naturalness'

export interface Correction {
  id: string
  original: string
  corrected: string
  explanation: string
  category: CorrectionCategory
  /** Full learner message the correction came from. */
  source: string
  turn: number
}

export interface VocabularyItem {
  id: string
  term: string
  meaning: string
  example: string
  turn: number
}

export interface LearningProgress {
  turns: number
  corrections: number
  vocabulary: number
  by_category: Record<CorrectionCategory, number>
}

export interface LearningState {
  /** False when the server has the analysis turned off. */
  enabled: boolean
  turns: number
  corrections: Correction[]
  vocabulary: VocabularyItem[]
  progress: LearningProgress
}

export const EMPTY_LEARNING: LearningState = {
  enabled: true,
  turns: 0,
  corrections: [],
  vocabulary: [],
  progress: {
    turns: 0,
    corrections: 0,
    vocabulary: 0,
    by_category: { grammar: 0, vocabulary: 0, naturalness: 0 },
  },
}

/** Tolerate partial payloads so a malformed event never breaks the screen. */
export function toLearningState(value: unknown): LearningState {
  const raw = (value ?? {}) as Partial<LearningState>
  return {
    ...EMPTY_LEARNING,
    ...raw,
    corrections: Array.isArray(raw.corrections) ? raw.corrections : [],
    vocabulary: Array.isArray(raw.vocabulary) ? raw.vocabulary : [],
    progress: { ...EMPTY_LEARNING.progress, ...(raw.progress ?? {}) },
  }
}
