const SERIES_COLORS = [
  '#2563eb',
  '#0f766e',
  '#7c3aed',
  '#c2410c',
  '#be123c',
  '#4d7c0f',
] as const

export function seriesColor(key: string): string {
  let hash = 0
  for (const char of key) hash = (hash * 31 + char.codePointAt(0)!) | 0
  return SERIES_COLORS[Math.abs(hash) % SERIES_COLORS.length]
}
