const STORAGE_KEY = 'english-coach.threadId'

function newId(): string {
  // randomUUID only exists in secure contexts (HTTPS / localhost).
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** One conversation id per device, shared by the chat and voice channels. */
export function getThreadId(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return stored
    const created = `thread-${newId()}`
    localStorage.setItem(STORAGE_KEY, created)
    return created
  } catch {
    return 'default'
  }
}

/** Start a new conversation: returns a fresh id and remembers it. */
export function resetThreadId(): string {
  const created = `thread-${newId()}`
  try {
    localStorage.setItem(STORAGE_KEY, created)
  } catch {
    // Storage unavailable: the id only lives for this page load.
  }
  return created
}
