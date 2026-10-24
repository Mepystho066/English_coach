export const env = {
  API_URL: (import.meta as any).env.VITE_API_URL || 'http://192.168.40.9:8000',
} as const
