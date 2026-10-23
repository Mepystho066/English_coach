export const env = {
  API_URL: (import.meta as any).env.VITE_API_URL || 'http://127.0.0.1:7932',
} as const
