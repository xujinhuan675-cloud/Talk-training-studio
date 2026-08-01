import { useEffect, useState } from 'react'
import {
  fetchPersonas,
  fetchScenarios,
  fetchOrganizations,
  fetchRelationships,
  createRoom,
  type PersonaSummary,
  type PersonaRelationship,
  type Scenario,
} from '../services/api'
import { useI18n } from '../i18n'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from './ui/dialog'
import { Field, Input, Select } from './ui/form'
import './CreateRoomDialog.css'

interface CreateRoomDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (roomId: number) => void
}

export default function CreateRoomDialog({ open, onClose, onCreated }: CreateRoomDialogProps) {
  const { tr } = useI18n()
  const [personas, setPersonas] = useState<PersonaSummary[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [relationships, setRelationships] = useState<PersonaRelationship[]>([])
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [type, setType] = useState<'private' | 'group'>('private')
  const [selectedPersonas, setSelectedPersonas] = useState<string[]>([])
  const [recommendedPersonas, setRecommendedPersonas] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      fetchPersonas().then(setPersonas).catch(() => {})
      fetchScenarios().then(setScenarios).catch(() => {})
      // Load relationships for smart recommendations
      fetchOrganizations().then((orgs) => {
        if (orgs.length > 0) {
          fetchRelationships(orgs[0].id).then(setRelationships).catch(() => {})
        }
      }).catch(() => {})
      // Reset form
      setName('')
      setType('private')
      setSelectedPersonas([])
      setRecommendedPersonas([])
      setSelectedScenarioId(null)
      setError(null)
    }
  }, [open])

  // Update recommendations when selected personas change
  useEffect(() => {
    if (selectedPersonas.length === 0 || relationships.length === 0) {
      setRecommendedPersonas([])
      return
    }
    const related = new Set<string>()
    for (const pid of selectedPersonas) {
      for (const r of relationships) {
        if (r.from_persona_id === pid && !selectedPersonas.includes(r.to_persona_id)) {
          related.add(r.to_persona_id)
        }
        if (r.to_persona_id === pid && !selectedPersonas.includes(r.from_persona_id)) {
          related.add(r.from_persona_id)
        }
      }
    }
    setRecommendedPersonas([...related])
  }, [selectedPersonas, relationships])

  const handleScenarioChange = (scenarioId: number | null) => {
    setSelectedScenarioId(scenarioId)
    if (scenarioId !== null) {
      const scenario = scenarios.find((s) => s.id === scenarioId)
      if (scenario && scenario.suggested_persona_ids.length > 0) {
        setSelectedPersonas(scenario.suggested_persona_ids)
        if (scenario.suggested_persona_ids.length >= 2) {
          setType('group')
        }
      }
    }
  }

  const togglePersona = (id: string) => {
    if (type === 'private') {
      // Private: single select
      setSelectedPersonas((prev) => (prev.includes(id) ? [] : [id]))
    } else {
      // Group: multi select
      setSelectedPersonas((prev) =>
        prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
      )
    }
  }

  // When switching type, reset selection if it violates constraints
  useEffect(() => {
    if (type === 'private') {
      setSelectedPersonas((current) => (current.length > 1 ? [current[0]] : current))
    }
  }, [type])

  const isValid = () => {
    if (!name.trim()) return false
    if (type === 'private' && selectedPersonas.length !== 1) return false
    if (type === 'group' && selectedPersonas.length < 2) return false
    return true
  }

  const handleSubmit = async () => {
    if (!isValid()) return
    setSubmitting(true)
    setError(null)
    try {
      const room = await createRoom({
        name: name.trim(),
        type,
        persona_ids: selectedPersonas,
        ...(selectedScenarioId != null ? { scenario_id: selectedScenarioId } : {}),
      })
      onCreated(room.id)
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tr('创建失败，请重试', 'Creation failed. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <DialogContent className="create-room-dialog" aria-describedby={undefined}>
        <DialogTitle className="create-room-title">
          {tr('创建对话房间', 'Create conversation room')}
        </DialogTitle>
        <div className="dialog-body">
          <Field className="field-label" label={tr('名称', 'Name')}>
            <Input
              name="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tr('输入对话房间名称', 'Enter conversation room name')}
              autoFocus
            />
          </Field>

          <Field className="field-label" label={tr('类型', 'Type')}>
            <Select
              name="type"
              value={type}
              onChange={(e) => setType(e.target.value as 'private' | 'group')}
            >
              <option value="private">{tr('私聊', 'Private')}</option>
              <option value="group">{tr('群聊', 'Group')}</option>
            </Select>
          </Field>

          {scenarios.length > 0 && (
            <Field className="field-label" label={tr('场景（可选）', 'Scenario (optional)')}>
              <Select
                value={selectedScenarioId ?? ''}
                onChange={(e) =>
                  handleScenarioChange(e.target.value ? Number(e.target.value) : null)
                }
              >
                <option value="">{tr('不使用场景', 'No scenario')}</option>
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <div className="field-label">
            {tr('选择角色', 'Choose Personas')} {type === 'private' ? tr('(选择 1 个)', '(choose 1)') : tr('(至少 2 个)', '(at least 2)')}
          </div>
          <div className="persona-select-list">
            {personas.map((p) => (
              <div
                key={p.id}
                className={`persona-select-item ${selectedPersonas.includes(p.id) ? 'selected' : ''}`}
                onClick={() => togglePersona(p.id)}
              >
                <span
                  className="persona-color"
                  style={{ backgroundColor: '#94a3b8' }}
                />
                <span className="persona-select-name">{p.name}</span>
                <span className="persona-select-role">{p.role}</span>
              </div>
            ))}
          </div>

          {type === 'group' && recommendedPersonas.length > 0 && (
            <div className="persona-recommendations">
              <div className="field-label persona-recommendations-label">
                {tr('推荐添加（有关系的角色）', 'Recommended additions (related personas)')}
              </div>
              <div className="persona-recommendation-list">
                {recommendedPersonas.map((pid) => {
                  const p = personas.find((pp) => pp.id === pid)
                  if (!p) return null
                  return (
                    <Button
                      key={pid}
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setSelectedPersonas((prev) => [...prev, pid])
                      }}
                    >
                      + {p.name}
                    </Button>
                  )
                })}
              </div>
            </div>
          )}

          {error && <div className="dialog-error">{error}</div>}
        </div>

        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose}>
            {tr('取消', 'Cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!isValid() || submitting}
          >
            {submitting ? tr('创建中...', 'Creating...') : tr('创建', 'Create')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
