import { useEffect, useState } from 'react'
import {
  fetchScenarios,
  fetchPersonas,
  createScenario,
  updateScenario,
  deleteScenario,
  type Scenario,
  type PersonaSummary,
} from '../services/api'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from './ui/dialog'
import { Field, Input, Textarea } from './ui/form'
import './ScenarioDialog.css'

interface ScenarioDialogProps {
  open: boolean
  onClose: () => void
}

const getErrorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : 'Operation failed'

export default function ScenarioDialog({ open, onClose }: ScenarioDialogProps) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [personas, setPersonas] = useState<PersonaSummary[]>([])
  const [editing, setEditing] = useState<Scenario | null>(null)
  const [isNew, setIsNew] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [contextPrompt, setContextPrompt] = useState('')
  const [suggestedPersonaIds, setSuggestedPersonaIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const loadData = async () => {
    try {
      const [s, p] = await Promise.all([fetchScenarios(), fetchPersonas()])
      setScenarios(s)
      setPersonas(p)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    if (open) {
      loadData()
      setEditing(null)
      setIsNew(false)
      setError(null)
    }
  }, [open])

  const startEdit = (scenario: Scenario) => {
    setEditing(scenario)
    setIsNew(false)
    setName(scenario.name)
    setDescription(scenario.description)
    setContextPrompt(scenario.context_prompt)
    setSuggestedPersonaIds([...scenario.suggested_persona_ids])
    setError(null)
  }

  const startCreate = () => {
    setEditing(null)
    setIsNew(true)
    setName('')
    setDescription('')
    setContextPrompt('')
    setSuggestedPersonaIds([])
    setError(null)
  }

  const togglePersona = (id: string) => {
    setSuggestedPersonaIds((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id],
    )
  }

  const handleSave = async () => {
    if (!name.trim() || !contextPrompt.trim()) {
      setError('名称和上下文提示词不能为空')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      if (isNew) {
        await createScenario({
          name: name.trim(),
          description: description.trim(),
          context_prompt: contextPrompt.trim(),
          suggested_persona_ids: suggestedPersonaIds,
        })
      } else if (editing) {
        await updateScenario(editing.id, {
          name: name.trim(),
          description: description.trim(),
          context_prompt: contextPrompt.trim(),
          suggested_persona_ids: suggestedPersonaIds,
        })
      }
      await loadData()
      setEditing(null)
      setIsNew(false)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!editing) return
    if (!confirm(`确定删除场景「${editing.name}」？`)) return
    setSubmitting(true)
    try {
      await deleteScenario(editing.id)
      await loadData()
      setEditing(null)
      setIsNew(false)
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  const showForm = isNew || editing !== null

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <DialogContent className="scenario-dialog" aria-describedby={undefined}>
        <DialogTitle className="scenario-dialog-title">场景管理</DialogTitle>
        <div className="dialog-body">
          <Button className="add-scenario-btn" variant="secondary" onClick={startCreate}>
            + 新建场景
          </Button>

          <div className="scenario-list-panel">
            {scenarios.length === 0 ? (
              <div className="scenario-list-empty">
                暂无场景
              </div>
            ) : (
              scenarios.map((s) => (
                <div
                  key={s.id}
                  className={`scenario-list-item ${editing?.id === s.id ? 'selected' : ''}`}
                  onClick={() => startEdit(s)}
                >
                  <span className="scenario-list-item-name">{s.name}</span>
                  {s.description && (
                    <span className="scenario-list-item-desc">{s.description}</span>
                  )}
                </div>
              ))
            )}
          </div>

          {showForm && (
            <div className="scenario-form">
              <h4>{isNew ? '新建场景' : '编辑场景'}</h4>

              <Field className="field-label" label="名称">
                <Input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="场景名称"
                />
              </Field>

              <Field className="field-label" label="描述（可选）">
                <Input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="简短描述"
                />
              </Field>

              <Field className="field-label scenario-context-field" label="上下文提示词">
                <Textarea
                  value={contextPrompt}
                  onChange={(e) => setContextPrompt(e.target.value)}
                  placeholder="设定场景的上下文提示词..."
                />
              </Field>

              <div className="field-label">推荐角色（可选）</div>
              <div className="persona-checkbox-list">
                {personas.map((p) => (
                  <label key={p.id} className="persona-checkbox-item">
                    <input
                      type="checkbox"
                      checked={suggestedPersonaIds.includes(p.id)}
                      onChange={() => togglePersona(p.id)}
                    />
                    <span
                      className="persona-color"
                      style={{ backgroundColor: p.avatar_color || '#999' }}
                    />
                    <span>{p.name}</span>
                  </label>
                ))}
              </div>

              {error && <div className="dialog-error">{error}</div>}
            </div>
          )}
        </div>

        {showForm ? (
          <div className="dialog-actions">
            {editing && (
              <Button
                variant="danger"
                onClick={handleDelete}
                disabled={submitting}
              >
                删除
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(null)
                setIsNew(false)
                setError(null)
              }}
            >
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={submitting}
            >
              {submitting ? '保存中...' : '保存'}
            </Button>
          </div>
        ) : (
          <div className="dialog-actions">
            <Button variant="secondary" onClick={onClose}>
              关闭
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
