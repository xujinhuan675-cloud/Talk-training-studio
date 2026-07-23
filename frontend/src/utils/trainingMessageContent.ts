const COACHING_NOTE_MARKERS = [
  '小提醒',
  '提醒',
  '更好可以说',
  '更好的说法',
  '更强改写',
  '改写建议',
  '你再试一次',
  '请再试一次',
  'better rewrite',
  'better version',
  'hint',
  'quick hint',
  'suggestion',
  'try again',
  'retry',
] as const

function markerIndex(text: string, marker: string): number {
  const lowerText = text.toLowerCase()
  const lowerMarker = marker.toLowerCase()
  const candidates = [
    `\n${lowerMarker}:`,
    `\n${lowerMarker}：`,
    `\n- ${lowerMarker}:`,
    `\n- ${lowerMarker}：`,
    `\n* ${lowerMarker}:`,
    `\n* ${lowerMarker}：`,
  ]

  for (const candidate of candidates) {
    const index = lowerText.indexOf(candidate)
    if (index >= 0) return index
  }

  if (lowerText.startsWith(`${lowerMarker}:`) || lowerText.startsWith(`${lowerMarker}：`)) {
    return 0
  }

  return -1
}

export function stripTrainingCoachNotesFromCounterpart(content: string): string {
  let firstIndex = -1
  for (const marker of COACHING_NOTE_MARKERS) {
    const index = markerIndex(content, marker)
    if (index >= 0 && (firstIndex < 0 || index < firstIndex)) {
      firstIndex = index
    }
  }

  if (firstIndex < 0) return content
  return content.slice(0, firstIndex).trimEnd()
}
