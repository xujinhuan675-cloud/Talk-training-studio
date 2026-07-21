import { useEffect, useState } from 'react'
import {
  fetchPersonaDetail,
  fetchTeams,
  createPersona,
  updatePersona,
  deletePersona,
  type PersonaSummary,
  type Organization,
  type Team,
} from '../services/api'
import Avatar from './Avatar'
import { useI18n } from '../i18n'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from './ui/dialog'
import { Input, Select, Textarea } from './ui/form'
import './PersonaEditorDialog.css'

interface PersonaEditorDialogProps {
  open: boolean
  onClose: () => void
  onSaved: () => void
  editingPersona?: PersonaSummary | null
  currentOrg?: Organization | null
}

export default function PersonaEditorDialog({
  open,
  onClose,
  onSaved,
  editingPersona,
  currentOrg,
}: PersonaEditorDialogProps) {
  const { tr } = useI18n()
  const isEdit = !!editingPersona

  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [avatarColor, setAvatarColor] = useState('#888888')
  const [content, setContent] = useState('')
  const [teamId, setTeamId] = useState<number | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    setSubmitting(false)

    // Load teams if org exists
    if (currentOrg) {
      fetchTeams(currentOrg.id).then(setTeams).catch(() => setTeams([]))
    } else {
      setTeams([])
    }

    if (editingPersona) {
      setId(editingPersona.id)
      setName(editingPersona.name)
      setRole(editingPersona.role)
      setAvatarColor(editingPersona.avatar_color || '#888888')
      setTeamId(editingPersona.team_id)
      setContent('')
      setLoading(true)
      fetchPersonaDetail(editingPersona.id)
        .then((detail) => {
          setContent(detail.content || '')
        })
        .catch(() => {
          setContent('')
        })
        .finally(() => setLoading(false))
    } else {
      setId('')
      setName('')
      setRole('')
      setAvatarColor('#888888')
      setTeamId(null)
      setContent('')
      setLoading(false)
    }
  }, [open, editingPersona])

  const handleSave = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const orgFields = {
        organization_id: currentOrg?.id ?? null,
        team_id: teamId,
      }
      if (isEdit) {
        await updatePersona(editingPersona!.id, {
          name,
          role,
          avatar_color: avatarColor,
          content,
          ...orgFields,
        })
      } else {
        if (!id.trim()) {
          setError(tr('ID 不能为空', 'ID is required'))
          setSubmitting(false)
          return
        }
        await createPersona({
          id: id.trim(),
          name,
          role,
          avatar_color: avatarColor,
          content,
          ...orgFields,
        })
      }
      onSaved()
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!editingPersona) return
    if (!confirm(tr('确定删除角色「{name}」？', 'Delete persona “{name}”?', { name: editingPersona.name }))) return
    setSubmitting(true)
    try {
      await deletePersona(editingPersona.id)
      onSaved()
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
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
      <DialogContent className="persona-editor-dialog" aria-describedby={undefined}>
        <DialogTitle asChild className="persona-editor-title">
          <h3>{isEdit ? tr('编辑角色', 'Edit Persona') : tr('新建角色', 'New Persona')}</h3>
        </DialogTitle>
        <div className="dialog-body">
          <div className="persona-avatar-preview">
            <Avatar name={name || '?'} color={avatarColor} size={48} />
          </div>

          <label className="field-label">
            ID
            <Input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder={tr('英文标识符，如 ceo', 'English identifier, e.g. ceo')}
              disabled={isEdit}
              autoFocus={!isEdit}
            />
          </label>

          <label className="field-label">
            {tr('名称', 'Name')}
            <Input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tr('角色显示名称', 'Persona display name')}
            />
          </label>

          <label className="field-label">
            {tr('角色', 'Role')}
            <Input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder={tr('如：CEO、产品经理', 'Example: CEO, Product Manager')}
            />
          </label>

          <label className="field-label">
            {tr('头像颜色', 'Avatar Color')}
            <div className="color-field">
              <input
                type="color"
                value={avatarColor}
                onChange={(e) => setAvatarColor(e.target.value)}
              />
              <span className="color-value">{avatarColor}</span>
            </div>
          </label>

          {teams.length > 0 && (
            <label className="field-label">
              {tr('所属团队', 'Team')}
              <Select
                value={teamId ?? ''}
                onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{tr('不指定', 'None')}</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            </label>
          )}

          <label className="field-label">
            {tr('内容（Markdown）', 'Content (Markdown)')}
            <Textarea
              value={loading ? tr('加载中...', 'Loading...') : content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={tr('角色画像的详细内容...', 'Detailed persona profile...')}
              disabled={loading}
            />
          </label>

          {error && <div className="dialog-error">{error}</div>}
        </div>

        <div className="dialog-actions">
          {isEdit && (
            <Button
              className="persona-editor-delete"
              variant="danger"
              onClick={handleDelete}
              disabled={submitting}
            >
              {tr('删除', 'Delete')}
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            {tr('取消', 'Cancel')}
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={submitting || loading}
          >
            {submitting ? tr('保存中...', 'Saving...') : tr('保存', 'Save')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
