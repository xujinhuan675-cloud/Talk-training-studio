import { Users, MessageSquare, ChevronRight } from 'lucide-react'
import type { DetectedSpeaker } from '../services/api'
import { useI18n, type TranslationKey } from '../i18n'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import './SpeakerSelector.css'

interface Props {
  speakers: DetectedSpeaker[]
  selected: Set<string>
  onToggle: (name: string) => void
  onConfirm: () => void
  onSkip: () => void
  disabled?: boolean
}

const DOMINANCE_BADGE: Record<string, { labelKey: TranslationKey; cls: string }> = {
  high: { labelKey: 'speaker.dominance.high', cls: 'badge-high' },
  medium: { labelKey: 'speaker.dominance.medium', cls: 'badge-medium' },
  low: { labelKey: 'speaker.dominance.low', cls: 'badge-low' },
}

export default function SpeakerSelector({
  speakers,
  selected,
  onToggle,
  onConfirm,
  onSkip,
  disabled,
}: Props) {
  const { t, tr } = useI18n()

  return (
    <div className="speaker-selector">
      <div className="speaker-header">
        <Users size={18} />
        <h3>{tr('检测到 {count} 位说话人', 'Detected {count} speakers', { count: speakers.length })}</h3>
      </div>
      <p className="speaker-hint">{tr('选择要生成对手画像的人（可多选）', 'Choose who to turn into opponent profiles (multi-select)')}</p>

      <div className="speaker-list">
        {speakers.map((s) => {
          const isSelected = selected.has(s.name)
          const badge = DOMINANCE_BADGE[s.dominance_level] || DOMINANCE_BADGE.medium
          return (
            <label
              key={s.name}
              className={`speaker-card${isSelected ? ' selected' : ''}${disabled ? ' disabled' : ''}`}
            >
              <Checkbox
                className="speaker-checkbox"
                checked={isSelected}
                onChange={() => onToggle(s.name)}
                disabled={disabled}
                aria-label={tr('选择 {name}', 'Select {name}', { name: s.name })}
              />
              <div className="speaker-info">
                <div className="speaker-name-row">
                  <span className="speaker-name">{s.name}</span>
                  {s.role && <span className="speaker-role">{s.role}</span>}
                  <span className={`speaker-badge ${badge.cls}`}>{t(badge.labelKey)}</span>
                </div>
                <div className="speaker-meta">
                  <MessageSquare size={12} />
                  <span>{tr('{count} 次发言', '{count} turns', { count: s.speaking_turns })}</span>
                </div>
                {s.sample_quote && (
                  <div className="speaker-quote">"{s.sample_quote}"</div>
                )}
              </div>
            </label>
          )
        })}
      </div>

      <div className="speaker-actions">
        <Button
          variant="primary"
          className="speaker-confirm"
          onClick={onConfirm}
          disabled={disabled || selected.size === 0}
        >
          {tr('为选中的 {count} 人生成画像', 'Generate profiles for {count} selected', { count: selected.size })}
          <ChevronRight size={14} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="speaker-skip"
          onClick={onSkip}
          disabled={disabled}
        >
          {tr('跳过，直接分析全部素材', 'Skip and analyze all materials')}
        </Button>
      </div>
    </div>
  )
}
