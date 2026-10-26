export const env = {
  // Empty means same origin: the Vite dev server proxies /api to the backend.
  API_URL: ((import.meta as any).env.VITE_API_URL || '') as string,
} as const
