function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function getErrorMessage(error: unknown, fallback = 'Request failed'): string {
  if (error instanceof Error && error.message.trim()) return error.message
  if (typeof error === 'string' && error.trim()) return error
  if (Array.isArray(error)) {
    const messages = error
      .map((item) => getErrorMessage(item, ''))
      .filter(Boolean)
    return messages.length ? messages.join('; ') : fallback
  }
  if (isRecord(error)) {
    for (const key of ['message', 'detail', 'details', 'error', 'reason']) {
      const message = getErrorMessage(error[key], '')
      if (message) return message
    }
    try {
      return JSON.stringify(error)
    } catch {
      return fallback
    }
  }
  return fallback
}

