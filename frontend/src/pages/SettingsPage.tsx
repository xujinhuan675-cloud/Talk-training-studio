import { useCallback, useEffect, useState } from 'react'
import {
  Plus,
  Pencil,
  Trash2,
  Eye,
  Users,
  Layers,
  Building2,
  ClipboardList,
  Volume2,
  Sparkles,
  Mic,
  Radio,
  RefreshCw,
  Save,
  KeyRound,
} from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppContext } from '../contexts/AppContext'
import Avatar from '../components/Avatar'
import PersonaEditorDialog from '../components/PersonaEditorDialog'
import {
  updatePersona,
  deletePersona,
  fetchScenarios,
  fetchPersonas,
  createScenario,
  updateScenario,
  deleteScenario,
  fetchOrganizations,
  fetchOrganizationDetail,
  createOrganization,
  updateOrganization,
  deleteOrganization,
  createTeam,
  deleteTeam,
  fetchRelationships,
  createRelationship,
  deleteRelationship,
  type PersonaSummary,
  type Scenario,
  type Organization,
  type Team,
  type PersonaRelationship,
} from '../services/api'
import {
  fetchVoiceConfig,
  saveVoiceConfig,
  type VoicePreferenceConfig,
} from '../services/voiceConfig'
import ConfirmDialog from '../components/layout/ConfirmDialog'
import { Button } from '../components/ui/button'
import { Field, Input, Select, Textarea } from '../components/ui/form'
import { SegmentedControl } from '../components/ui/segmented-control'
import { useI18n, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import './SettingsPage.css'

/** Reusable confirm dialog state hook */
function useConfirmDialog() {
  const [state, setState] = useState<{
    open: boolean; title: string; message: string; onConfirm: () => void
  }>({ open: false, title: '', message: '', onConfirm: () => {} })

  const ask = useCallback((title: string, message: string, onConfirm: () => void) => {
    setState({ open: true, title, message, onConfirm })
  }, [])

  const close = useCallback(() => {
    setState((s) => ({ ...s, open: false }))
  }, [])

  const confirm = () => {
    state.onConfirm()
    close()
  }

  return { ...state, ask, close, confirm }
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

type TabKey = 'personas' | 'scenarios' | 'organizations' | 'config'
type SettingsTabKey = TabKey | 'training'

const TABS: { key: SettingsTabKey; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: 'personas', labelKey: 'settings.tabs.personas', icon: <Users size={14} /> },
  { key: 'scenarios', labelKey: 'settings.tabs.scenarios', icon: <Layers size={14} /> },
  { key: 'organizations', labelKey: 'settings.tabs.organizations', icon: <Building2 size={14} /> },
  { key: 'training', labelKey: 'settings.tabs.training', icon: <ClipboardList size={14} /> },
  { key: 'config', labelKey: 'settings.tabs.config', icon: <KeyRound size={14} /> },
]

const SETTINGS_TAB_KEYS: readonly TabKey[] = ['personas', 'scenarios', 'organizations', 'config']

export function SettingsShell({
  activeTab,
  children,
}: {
  activeTab: SettingsTabKey
  children: React.ReactNode
}) {
  const { t } = useI18n()
  const navigate = useNavigate()

  const selectTab = (tab: SettingsTabKey) => {
    if (tab === 'training') {
      navigate(APP_ROUTES.configScenarios)
      return
    }
    navigate(`${APP_ROUTES.config}?tab=${tab}`)
  }

  return (
    <div className="settings-page">
      <div className="settings-tab-bar">
        <SegmentedControl
          ariaLabel={t('nav.settings')}
          className="settings-tabs-control"
          value={activeTab}
          onValueChange={selectTab}
          options={TABS.map((tab) => ({
            value: tab.key,
            label: (
              <span className="settings-tab-label">
                {tab.icon}
                <span>{t(tab.labelKey)}</span>
              </span>
            ),
          }))}
        />
      </div>

      <div className="settings-content">
        {children}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Personas Tab
// ---------------------------------------------------------------------------

function PersonasTab() {
  const navigate = useNavigate()
  const { t, tr } = useI18n()
  const { personaMap, currentOrg, reloadPersonas } = useAppContext()
  const personas = Object.values(personaMap)
  const dialog = useConfirmDialog()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<PersonaSummary | null>(null)

  const startCreate = () => {
    setEditing(null)
    setDialogOpen(true)
  }

  const startEdit = (persona: PersonaSummary) => {
    setEditing(persona)
    setDialogOpen(true)
  }

  const handleDialogClose = () => {
    setDialogOpen(false)
    setEditing(null)
  }

  const handleSaved = () => {
    reloadPersonas()
  }

  return (
    <>
      <div className="settings-section-header">
        <h3 className="settings-section-title">{tr('角色', 'Personas')}</h3>
        <div className="settings-header-actions">
          <Button
            variant="secondary"
            className="persona-build-btn"
            onClick={() => navigate(APP_ROUTES.configPersonaNew)}
            title={tr('从素材生成角色', 'Generate personas from source material')}
          >
            <Sparkles size={14} />
            {tr('导入素材', 'Import Material')}
          </Button>
          <Button className="settings-create-btn" variant="primary" onClick={startCreate}>
            <Plus size={14} />
            {tr('新建角色', 'New Persona')}
          </Button>
        </div>
      </div>

      <div className="settings-list">
        {personas.length === 0 && (
          <div className="settings-empty">
            <div className="settings-empty-icon">
              <Users size={36} />
            </div>
            <p>{tr('暂无角色', 'No personas yet')}</p>
          </div>
        )}
        {personas.map((p) => (
          <div
            key={p.id}
            className={`settings-list-item${editing?.id === p.id ? ' selected' : ''}`}
            onClick={() => navigate(APP_ROUTES.configPersonaEdit(p.id))}
          >
            <div className="settings-item-avatar">
              <Avatar name={p.name} color={p.avatar_color || '#0F766E'} size={40} />
            </div>
            <div className="settings-item-info">
              <div className="settings-item-name">{p.name}</div>
              <div className="settings-item-role">{p.role}</div>
            </div>
            <div className="settings-item-actions">
              <Button
                variant="secondary"
                size="icon"
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); navigate(APP_ROUTES.configPersonaEdit(p.id)) }}
                title={tr('查看详情', 'View details')}
              >
                <Eye size={14} />
              </Button>
              <Button
                variant="secondary"
                size="icon"
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); startEdit(p) }}
                title={tr('编辑', 'Edit')}
              >
                <Pencil size={14} />
              </Button>
              <Button
                variant="danger"
                size="icon"
                className="settings-item-btn danger"
                onClick={(e) => {
                  e.stopPropagation()
                  dialog.ask(
                    tr('删除角色', 'Delete Persona'),
                    tr('确定删除角色「{name}」？此操作无法撤销。', 'Delete persona “{name}”? This cannot be undone.', { name: p.name }),
                    () => {
                    deletePersona(p.id).then(() => reloadPersonas())
                    },
                  )
                }}
                title={t('common.delete')}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          </div>
        ))}
      </div>

      <PersonaEditorDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        onSaved={handleSaved}
        editingPersona={editing}
        currentOrg={currentOrg}
      />
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={t('common.delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Scenarios Tab
// ---------------------------------------------------------------------------

function ScenariosTab() {
  const { t, tr } = useI18n()
  const { personaMap, reloadScenarios } = useAppContext()
  const dialog = useConfirmDialog()

  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [allPersonas, setAllPersonas] = useState<PersonaSummary[]>([])
  const [editing, setEditing] = useState<Scenario | null>(null)
  const [isNew, setIsNew] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [contextPrompt, setContextPrompt] = useState('')
  const [suggestedPersonaIds, setSuggestedPersonaIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const showForm = isNew || editing !== null

  const loadData = async () => {
    try {
      const [s, p] = await Promise.all([fetchScenarios(), fetchPersonas()])
      setScenarios(s)
      setAllPersonas(p)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const startCreate = () => {
    setEditing(null)
    setIsNew(true)
    setName('')
    setDescription('')
    setContextPrompt('')
    setSuggestedPersonaIds([])
    setError(null)
  }

  const startEdit = (scenario: Scenario) => {
    setEditing(scenario)
    setIsNew(false)
    setName(scenario.name)
    setDescription(scenario.description)
    setContextPrompt(scenario.context_prompt)
    setSuggestedPersonaIds([...scenario.suggested_persona_ids])
    setError(null)
  }

  const handleCancel = () => {
    setEditing(null)
    setIsNew(false)
    setError(null)
  }

  const togglePersona = (pid: string) => {
    setSuggestedPersonaIds((prev) =>
      prev.includes(pid) ? prev.filter((p) => p !== pid) : [...prev, pid],
    )
  }

  const handleSave = async () => {
    if (!name.trim() || !contextPrompt.trim()) {
      setError(tr('名称和上下文提示词不能为空', 'Name and context prompt are required'))
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
      reloadScenarios()
      handleCancel()
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = () => {
    if (!editing) return
    dialog.ask(
      tr('删除对话场景', 'Delete room scenario'),
      tr('确定删除对话场景「{name}」？此操作无法撤销。', 'Delete room scenario “{name}”? This cannot be undone.', { name: editing.name }),
      async () => {
      setSubmitting(true)
      try {
        await deleteScenario(editing.id)
        await loadData()
        reloadScenarios()
        handleCancel()
      } catch (e: unknown) {
        setError(getErrorMessage(e))
      } finally {
        setSubmitting(false)
      }
      },
    )
  }

  return (
    <>
      <div className="settings-section-header">
        <h3 className="settings-section-title">{tr('对话场景', 'Room scenarios')}</h3>
        <Button className="settings-create-btn" variant="primary" onClick={startCreate}>
          <Plus size={14} />
          {tr('新建对话场景', 'New room scenario')}
        </Button>
      </div>

      <div className="settings-list">
        {scenarios.length === 0 && !showForm && (
          <div className="settings-empty">
            <div className="settings-empty-icon">
              <Layers size={36} />
            </div>
            <p>{tr('暂无对话场景', 'No room scenarios yet')}</p>
          </div>
        )}
        {scenarios.map((s) => (
          <div
            key={s.id}
            className={`settings-list-item${editing?.id === s.id ? ' selected' : ''}`}
            onClick={() => startEdit(s)}
          >
            <div className="settings-item-info">
              <div className="settings-item-name">{s.name}</div>
              {s.description && (
                <div className="settings-item-desc">{s.description}</div>
              )}
              {s.suggested_persona_ids.length > 0 && (
                <div className="settings-persona-chips">
                  {s.suggested_persona_ids.map((pid) => (
                    <span key={pid} className="settings-persona-chip">
                      {personaMap[pid]?.name || pid}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="settings-item-actions">
              <Button
                variant="secondary"
                size="icon"
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); startEdit(s) }}
                title={tr('编辑', 'Edit')}
              >
                <Pencil size={14} />
              </Button>
              <Button
                variant="danger"
                size="icon"
                className="settings-item-btn danger"
                onClick={(e) => {
                  e.stopPropagation()
                  dialog.ask(
                    tr('删除对话场景', 'Delete room scenario'),
                    tr('确定删除对话场景「{name}」？此操作无法撤销。', 'Delete room scenario “{name}”? This cannot be undone.', { name: s.name }),
                    () => {
                    deleteScenario(s.id).then(() => { loadData(); reloadScenarios() })
                    },
                  )
                }}
                title={t('common.delete')}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <div className="settings-form-panel">
          <h4>{isNew ? tr('新建对话场景', 'New room scenario') : tr('编辑对话场景', 'Edit room scenario')}</h4>

          <Field className="field-label" label={tr('名称', 'Name')}>
            <Input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tr('对话场景名称', 'Room scenario name')}
              autoFocus
            />
          </Field>

          <Field className="field-label" label={tr('描述（可选）', 'Description (optional)')}>
            <Input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={tr('短描述', 'Short description')}
            />
          </Field>

          <Field className="field-label" label={tr('上下文', 'Context')}>
            <Textarea
              value={contextPrompt}
              onChange={(e) => setContextPrompt(e.target.value)}
              placeholder={tr('对话背景和约束', 'Conversation context and constraints')}
            />
          </Field>

          <div className="field-label" style={{ marginBottom: 4 }}>{tr('关联角色', 'Linked Personas')}</div>
          <div className="settings-checkbox-list">
            {allPersonas.map((p) => (
              <label key={p.id} className="settings-checkbox-item">
                <input
                  type="checkbox"
                  checked={suggestedPersonaIds.includes(p.id)}
                  onChange={() => togglePersona(p.id)}
                />
                <span
                  className="settings-checkbox-color"
                  style={{ backgroundColor: p.avatar_color || '#999' }}
                />
                <span>{p.name}</span>
              </label>
            ))}
          </div>

          {error && <div className="settings-error">{error}</div>}

          <div className="settings-form-actions">
            {editing && (
              <Button className="btn-delete" variant="danger" onClick={handleDelete} disabled={submitting}>
                {t('common.delete')}
              </Button>
            )}
            <Button className="btn-cancel" variant="secondary" onClick={handleCancel}>{tr('取消', 'Cancel')}</Button>
            <Button
              className="btn-submit"
              variant="primary"
              onClick={handleSave}
              disabled={submitting}
            >
              {submitting ? t('common.saving') : t('common.save')}
            </Button>
          </div>
        </div>
      )}
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={t('common.delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Organizations Tab
// ---------------------------------------------------------------------------

const REL_LABELS: Record<string, { zh: string; en: string }> = {
  superior: { zh: '上级', en: 'Manager' },
  subordinate: { zh: '下级', en: 'Direct Report' },
  peer: { zh: '同级', en: 'Peer' },
  cross_department: { zh: '跨部门', en: 'Cross-functional' },
}

function OrganizationsTab() {
  const { t: translate, tr } = useI18n()
  const { reloadOrganizations, reloadPersonas } = useAppContext()
  const dialog = useConfirmDialog()
  const [personas, setPersonas] = useState<PersonaSummary[]>([])

  const [orgs, setOrgs] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [relationships, setRelationships] = useState<PersonaRelationship[]>([])
  const [orgTab, setOrgTab] = useState<'info' | 'teams' | 'relationships'>('info')

  // Org form state
  const [orgName, setOrgName] = useState('')
  const [orgIndustry, setOrgIndustry] = useState('')
  const [orgDescription, setOrgDescription] = useState('')
  const [orgContextPrompt, setOrgContextPrompt] = useState('')

  // Team add form
  const [newTeamName, setNewTeamName] = useState('')

  // Relationship add form
  const [relFrom, setRelFrom] = useState('')
  const [relTo, setRelTo] = useState('')
  const [relType, setRelType] = useState('peer')
  const [relDesc, setRelDesc] = useState('')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadOrgs = () => fetchOrganizations().then(setOrgs).catch(() => {})

  const loadOrgDetail = useCallback(async (orgId: number) => {
    const detail = await fetchOrganizationDetail(orgId)
    setSelectedOrg(detail.organization)
    setTeams(detail.teams)
    setOrgName(detail.organization.name)
    setOrgIndustry(detail.organization.industry)
    setOrgDescription(detail.organization.description)
    setOrgContextPrompt(detail.organization.context_prompt)
    fetchRelationships(orgId).then(setRelationships).catch(() => {})
  }, [])

  useEffect(() => {
    loadOrgs()
    fetchPersonas().then(setPersonas).catch(() => {})
    setError(null)
  }, [])

  useEffect(() => {
    if (orgs.length > 0 && !selectedOrg) {
      void loadOrgDetail(orgs[0].id)
    }
  }, [orgs, selectedOrg, loadOrgDetail])

  const handleNewOrg = () => {
    setSelectedOrg(null)
    setTeams([])
    setRelationships([])
    setOrgName('')
    setOrgIndustry('')
    setOrgDescription('')
    setOrgContextPrompt('')
    setOrgTab('info')
    setError(null)
  }

  const handleSaveOrg = async () => {
    setSaving(true)
    setError(null)
    try {
      if (selectedOrg) {
        await updateOrganization(selectedOrg.id, {
          name: orgName,
          industry: orgIndustry,
          description: orgDescription,
          context_prompt: orgContextPrompt,
        })
      } else {
        const created = await createOrganization({
          name: orgName,
          industry: orgIndustry,
          description: orgDescription,
          context_prompt: orgContextPrompt,
        })
        await loadOrgs()
        await loadOrgDetail(created.id)
      }
      reloadOrganizations()
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteOrg = () => {
    if (!selectedOrg) return
    dialog.ask(
      tr('删除组织', 'Delete Organization'),
      tr('确定删除组织「{name}」？所有关联的团队和关系数据将一并删除，此操作无法撤销。', 'Delete organization “{name}”? All related teams and relationship data will also be removed. This cannot be undone.', { name: selectedOrg.name }),
      async () => {
      try {
        await deleteOrganization(selectedOrg.id)
        setSelectedOrg(null)
        setTeams([])
        setRelationships([])
        setOrgName('')
        setOrgIndustry('')
        setOrgDescription('')
        setOrgContextPrompt('')
        await loadOrgs()
        reloadOrganizations()
        reloadPersonas()
      } catch (e: unknown) {
        setError(getErrorMessage(e))
      }
      },
    )
  }

  const handleAddTeam = async () => {
    if (!selectedOrg || !newTeamName.trim()) return
    try {
      await createTeam(selectedOrg.id, { name: newTeamName.trim() })
      setNewTeamName('')
      await loadOrgDetail(selectedOrg.id)
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const handleDeleteTeam = async (teamId: number) => {
    if (!selectedOrg) return
    try {
      await deleteTeam(selectedOrg.id, teamId)
      await loadOrgDetail(selectedOrg.id)
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const handleAddRelationship = async () => {
    if (!selectedOrg || !relFrom || !relTo || relFrom === relTo) return
    try {
      await createRelationship(selectedOrg.id, {
        from_persona_id: relFrom,
        to_persona_id: relTo,
        relationship_type: relType,
        description: relDesc,
      })
      setRelDesc('')
      fetchRelationships(selectedOrg.id).then(setRelationships)
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const handleDeleteRelationship = async (relId: number) => {
    if (!selectedOrg) return
    try {
      await deleteRelationship(selectedOrg.id, relId)
      fetchRelationships(selectedOrg.id).then(setRelationships)
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const assignedTeamIds = new Set(teams.map((t) => t.id))
  const unassignedPersonas = selectedOrg
    ? personas.filter((p) =>
        !p.team_id || !assignedTeamIds.has(p.team_id)
      ).filter((p) => p.id !== 'TEMPLATE')
    : []

  const handleAssignToTeam = async (personaId: string, tId: number) => {
    if (!selectedOrg) return
    try {
      await updatePersona(personaId, { organization_id: selectedOrg.id, team_id: tId })
      reloadPersonas()
      fetchPersonas().then(setPersonas).catch(() => {})
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const handleRemoveFromTeam = async (personaId: string) => {
    if (!selectedOrg) return
    try {
      await updatePersona(personaId, { team_id: null })
      reloadPersonas()
      fetchPersonas().then(setPersonas).catch(() => {})
    } catch (e: unknown) {
      setError(getErrorMessage(e))
    }
  }

  const personaName = (pid: string) => personas.find((p) => p.id === pid)?.name || pid
  const orgTabOptions = [
    { value: 'info' as const, label: tr('基础', 'Basics') },
    { value: 'teams' as const, label: tr('团队', 'Teams'), disabled: !selectedOrg },
    { value: 'relationships' as const, label: tr('关系', 'Relationships'), disabled: !selectedOrg },
  ]

  return (
    <>
      <div className="settings-section-header">
        <h3 className="settings-section-title">{tr('组织', 'Organizations')}</h3>
        <Button className="settings-create-btn" variant="primary" onClick={handleNewOrg}>
          <Plus size={14} />
          {tr('新建组织', 'New Organization')}
        </Button>
      </div>

      <div className="settings-org-layout">
        {/* Org selector if multiple */}
        {orgs.length > 1 && (
          <Select
            className="settings-org-selector"
            value={selectedOrg?.id ?? ''}
            onChange={(e) => e.target.value && loadOrgDetail(Number(e.target.value))}
          >
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </Select>
        )}

        {/* Org sub-tabs */}
        <SegmentedControl
          ariaLabel={tr('组织配置区域', 'Organization settings areas')}
          className="settings-org-tabs"
          options={orgTabOptions}
          size="sm"
          value={orgTab}
          onValueChange={(value) => setOrgTab(value)}
        />

        <div className="settings-form-panel" style={{ marginTop: 0 }}>
          {orgTab === 'info' && (
            <>
              <Field className="field-label" label={tr('名称', 'Name')}>
                <Input type="text" value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder={tr('Acme Corp', 'Acme Corp')} />
              </Field>
              <Field className="field-label" label={tr('行业', 'Industry')}>
                <Input type="text" value={orgIndustry} onChange={(e) => setOrgIndustry(e.target.value)} placeholder={tr('SaaS / 金融 / 制造', 'SaaS / Finance / Manufacturing')} />
              </Field>
              <Field className="field-label" label={tr('描述', 'Description')}>
                <Textarea value={orgDescription} onChange={(e) => setOrgDescription(e.target.value)} placeholder={tr('业务、产品、文化', 'Business, products, culture')} rows={3} />
              </Field>
              <Field className="field-label" label={tr('上下文', 'Context')}>
                <Textarea value={orgContextPrompt} onChange={(e) => setOrgContextPrompt(e.target.value)} placeholder={tr('角色共享的组织背景', 'Shared organization context')} rows={4} />
              </Field>

              <div className="settings-form-actions">
                {selectedOrg && (
                  <Button className="btn-delete" variant="danger" onClick={handleDeleteOrg}>{tr('删除组织', 'Delete Organization')}</Button>
                )}
                <Button className="btn-submit" variant="primary" onClick={handleSaveOrg} disabled={saving || !orgName.trim()}>
                  {saving ? translate('common.saving') : translate('common.save')}
                </Button>
              </div>
            </>
          )}

          {orgTab === 'teams' && selectedOrg && (
            <>
              {teams.length > 0 ? (
                <div className="team-list">
                  {teams.map((team) => {
                    const members = personas.filter((p) => p.team_id === team.id)
                    return (
                      <div key={team.id} className="team-item-block">
                        <div className="team-item">
                          <div className="team-item-info">
                            <div className="team-item-name">{team.name}</div>
                            {team.description && <div className="team-item-desc">{team.description}</div>}
                          </div>
                          <Button className="team-delete-btn" variant="danger" size="sm" onClick={() => handleDeleteTeam(team.id)}>{translate('common.delete')}</Button>
                        </div>
                        <div className="team-members">
                          {members.length > 0 ? (
                            members.map((p) => (
                              <span key={p.id} className="team-member-chip">
                                <span className="team-member-dot" style={{ background: p.avatar_color || '#999' }} />
                                {p.name}
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="team-member-remove"
                                  onClick={() => handleRemoveFromTeam(p.id)}
                                  aria-label={tr('移出团队', 'Remove from team')}
                                  title={tr('移出团队', 'Remove from team')}
                                >&times;</Button>
                              </span>
                            ))
                          ) : (
                            <span className="team-members-empty">{tr('暂无成员', 'No members')}</span>
                          )}
                          <Select
                            className="team-add-member-select"
                            value=""
                            onChange={(e) => e.target.value && handleAssignToTeam(e.target.value, team.id)}
                          >
                            <option value="">{tr('+ 添加角色', '+ Add Persona')}</option>
                            {unassignedPersonas.map((p) => (
                              <option key={p.id} value={p.id}>{p.name} ({p.role})</option>
                            ))}
                          </Select>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="empty-hint">{tr('暂无团队，添加第一个', 'No teams yet. Add the first one.')}</div>
              )}

              {unassignedPersonas.length > 0 && teams.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
                  {tr('未分配团队的角色：{names}', 'Personas without a team: {names}', {
                    names: unassignedPersonas.map((p) => p.name).join(tr('、', ', ')),
                  })}
                </div>
              )}

              <div className="add-team-form" style={{ marginTop: 10 }}>
                <Input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  placeholder={tr('团队名称', 'Team name')}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddTeam()}
                />
                <Button variant="primary" onClick={handleAddTeam} disabled={!newTeamName.trim()}>{tr('添加团队', 'Add Team')}</Button>
              </div>
            </>
          )}

          {orgTab === 'relationships' && selectedOrg && (
            <>
              {relationships.length > 0 ? (
                <div className="rel-list">
                  {relationships.map((r) => (
                    <div key={r.id} className="rel-item">
                      <span>
                        <strong>{personaName(r.from_persona_id)}</strong>
                        <span className={`rel-type-badge ${r.relationship_type}`}>
                          {REL_LABELS[r.relationship_type]
                            ? tr(REL_LABELS[r.relationship_type].zh, REL_LABELS[r.relationship_type].en)
                            : r.relationship_type}
                        </span>
                        <strong>{personaName(r.to_persona_id)}</strong>
                        {r.description && <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>-- {r.description}</span>}
                      </span>
                      <Button className="team-delete-btn" variant="danger" size="sm" onClick={() => handleDeleteRelationship(r.id)}>{translate('common.delete')}</Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-hint">{tr('暂无角色关系', 'No persona relationships yet')}</div>
              )}
              <div className="add-rel-form">
                <Select value={relFrom} onChange={(e) => setRelFrom(e.target.value)}>
                  <option value="">{tr('角色A', 'Persona A')}</option>
                  {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Select value={relType} onChange={(e) => setRelType(e.target.value)}>
                  <option value="superior">{tr('上级', 'Manager')}</option>
                  <option value="subordinate">{tr('下级', 'Direct Report')}</option>
                  <option value="peer">{tr('同级', 'Peer')}</option>
                  <option value="cross_department">{tr('跨部门', 'Cross-functional')}</option>
                </Select>
                <Select value={relTo} onChange={(e) => setRelTo(e.target.value)}>
                  <option value="">{tr('角色B', 'Persona B')}</option>
                  {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Input type="text" value={relDesc} onChange={(e) => setRelDesc(e.target.value)} placeholder={tr('描述（可选）', 'Description (optional)')} />
                <Button variant="primary" onClick={handleAddRelationship} disabled={!relFrom || !relTo || relFrom === relTo}>{tr('添加', 'Add')}</Button>
              </div>
            </>
          )}

          {error && <div className="settings-error">{error}</div>}
        </div>
      </div>
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={translate('common.delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Preferences Tab
// ---------------------------------------------------------------------------

interface VoicePreferenceForm {
  llmBaseUrl: string
  llmDefaultModel: string
  llmWireApi: string
  llmApiKey: string
  ttsProvider: string
  ttsBaseUrl: string
  ttsModel: string
  ttsApiKey: string
  sttProvider: string
  sttBaseUrl: string
  sttModel: string
  sttUseTtsApiKey: boolean
  sttApiKey: string
  realtimeApiKey: string
  realtimeModel: string
  realtimeVoice: string
  realtimeTranscriptionModel: string
}

const DEFAULT_VOICE_FORM: VoicePreferenceForm = {
  llmBaseUrl: 'https://ai.flowguide.cc',
  llmDefaultModel: 'gpt-5.5',
  llmWireApi: 'responses',
  llmApiKey: '',
  ttsProvider: 'openrouter',
  ttsBaseUrl: 'https://openrouter.ai/api/v1',
  ttsModel: 'mistralai/voxtral-mini-tts-2603',
  ttsApiKey: '',
  sttProvider: 'whisper',
  sttBaseUrl: 'https://openrouter.ai/api/v1',
  sttModel: 'openai/whisper-1',
  sttUseTtsApiKey: true,
  sttApiKey: '',
  realtimeApiKey: '',
  realtimeModel: 'gpt-realtime',
  realtimeVoice: 'marin',
  realtimeTranscriptionModel: 'gpt-realtime-whisper',
}

function toVoiceForm(config: VoicePreferenceConfig): VoicePreferenceForm {
  return {
    llmBaseUrl: config.llm_base_url || DEFAULT_VOICE_FORM.llmBaseUrl,
    llmDefaultModel: config.llm_default_model || DEFAULT_VOICE_FORM.llmDefaultModel,
    llmWireApi: config.llm_wire_api || DEFAULT_VOICE_FORM.llmWireApi,
    llmApiKey: '',
    ttsProvider: config.tts_provider || DEFAULT_VOICE_FORM.ttsProvider,
    ttsBaseUrl: config.tts_base_url || DEFAULT_VOICE_FORM.ttsBaseUrl,
    ttsModel: config.tts_model || DEFAULT_VOICE_FORM.ttsModel,
    ttsApiKey: '',
    sttProvider: config.stt_provider || DEFAULT_VOICE_FORM.sttProvider,
    sttBaseUrl: config.stt_base_url || DEFAULT_VOICE_FORM.sttBaseUrl,
    sttModel: config.stt_model || DEFAULT_VOICE_FORM.sttModel,
    sttUseTtsApiKey: config.stt_use_tts_api_key || config.stt_api_key_source !== 'stt',
    sttApiKey: '',
    realtimeApiKey: '',
    realtimeModel: config.realtime_model || DEFAULT_VOICE_FORM.realtimeModel,
    realtimeVoice: config.realtime_voice || DEFAULT_VOICE_FORM.realtimeVoice,
    realtimeTranscriptionModel: config.realtime_transcription_model || DEFAULT_VOICE_FORM.realtimeTranscriptionModel,
  }
}

function ConfigTab() {
  const { t, tr } = useI18n()
  const [config, setConfig] = useState<VoicePreferenceConfig | null>(null)
  const [form, setForm] = useState<VoicePreferenceForm>(DEFAULT_VOICE_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  const updateForm = (patch: Partial<VoicePreferenceForm>) => {
    setForm((current) => ({ ...current, ...patch }))
  }

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setNotice(null)
    try {
      const next = await fetchVoiceConfig()
      setConfig(next)
      setForm(toVoiceForm(next))
    } catch (err) {
      setNotice({ tone: 'error', text: getErrorMessage(err) })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const keyText = (configured: boolean, preview: string | null) => (
    configured
      ? tr('已配置 {preview}', 'Configured {preview}', { preview: preview || '' })
      : t('common.notConfigured')
  )

  const sourceText = (source: string) => {
    if (source === 'tts') return tr('复用 TTS key', 'Reuses TTS key')
    if (source === 'llm') return tr('回退到 LLM key', 'Falls back to LLM key')
    if (source === 'realtime') return tr('使用 Pipecat 实时服务专用 key', 'Uses dedicated Pipecat realtime service key')
    if (source === 'stt') return tr('使用 STT 专用 key', 'Uses dedicated STT key')
    return t('common.notConfigured')
  }

  const handleSave = async () => {
    setSaving(true)
    setNotice(null)
    try {
      const payload = {
        llm_base_url: form.llmBaseUrl,
        llm_default_model: form.llmDefaultModel,
        llm_wire_api: form.llmWireApi,
        ...(form.llmApiKey.trim() ? { llm_api_key: form.llmApiKey.trim() } : {}),
        tts_provider: form.ttsProvider,
        tts_base_url: form.ttsBaseUrl,
        tts_model: form.ttsModel,
        ...(form.ttsApiKey.trim() ? { tts_api_key: form.ttsApiKey.trim() } : {}),
        stt_provider: form.sttProvider,
        stt_base_url: form.sttBaseUrl,
        stt_model: form.sttModel,
        stt_use_tts_api_key: form.sttUseTtsApiKey,
        ...(!form.sttUseTtsApiKey && form.sttApiKey.trim() ? { stt_api_key: form.sttApiKey.trim() } : {}),
        realtime_model: form.realtimeModel,
        realtime_voice: form.realtimeVoice,
        realtime_transcription_model: form.realtimeTranscriptionModel,
        ...(form.realtimeApiKey.trim() ? { realtime_api_key: form.realtimeApiKey.trim() } : {}),
      }
      const next = await saveVoiceConfig(payload)
      setConfig(next)
      setForm(toVoiceForm(next))
      setNotice({ tone: 'success', text: tr('AI 配置已保存并重新加载', 'AI configuration saved and reloaded') })
    } catch (err) {
      setNotice({ tone: 'error', text: getErrorMessage(err) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="settings-section-header">
        <h3 className="settings-section-title">{tr('AI 服务', 'AI Services')}</h3>
        <Button
          className="settings-header-button"
          variant="secondary"
          size="sm"
          onClick={loadConfig}
          disabled={loading || saving}
        >
          <RefreshCw size={14} />
          {loading ? t('common.loading') : t('common.refresh')}
        </Button>
      </div>

      <div className="settings-voice-status">
        <div className="settings-voice-status-item">
          <KeyRound size={18} />
          <span>{tr('LLM', 'LLM')}</span>
          <strong>{config ? keyText(config.llm_api_key_configured, config.llm_api_key_preview) : t('common.loading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Volume2 size={18} />
          <span>{tr('TTS', 'TTS')}</span>
          <strong>{config ? keyText(config.tts_api_key_configured, config.tts_api_key_preview) : t('common.loading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Mic size={18} />
          <span>{tr('STT', 'STT')}</span>
          <strong>{config ? sourceText(config.stt_api_key_source) : t('common.loading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Radio size={18} />
          <span>{tr('实时语音', 'Realtime')}</span>
          <strong>{config ? sourceText(config.realtime_api_key_source) : t('common.loading')}</strong>
        </div>
      </div>

      {notice && (
        <div className={notice.tone === 'error' ? 'settings-error' : 'settings-success'}>
          {notice.text}
        </div>
      )}

      <div className="settings-voice-grid">
        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <KeyRound size={18} />
            <h4>{tr('LLM', 'LLM')}</h4>
          </div>
          <Field className="settings-voice-field" label={tr('基础 URL', 'Base URL')}>
            <Input value={form.llmBaseUrl} onChange={(e) => updateForm({ llmBaseUrl: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('模型', 'Model')}>
            <Input value={form.llmDefaultModel} onChange={(e) => updateForm({ llmDefaultModel: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('接口', 'API')}>
            <Select value={form.llmWireApi} onChange={(e) => updateForm({ llmWireApi: e.target.value })}>
              <option value="responses">{tr('Responses 接口', 'Responses')}</option>
              <option value="chat_completions">{tr('Chat Completions 接口', 'Chat Completions')}</option>
            </Select>
          </Field>
          <Field className="settings-voice-field" label={tr('API 密钥', 'API Key')}>
            <Input
              type="password"
              value={form.llmApiKey}
              onChange={(e) => updateForm({ llmApiKey: e.target.value })}
              placeholder={config?.llm_api_key_configured ? keyText(true, config.llm_api_key_preview) : t('common.enterToSave')}
              autoComplete="off"
            />
          </Field>
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Volume2 size={18} />
            <h4>{tr('TTS', 'TTS')}</h4>
          </div>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            <Select value={form.ttsProvider} onChange={(e) => updateForm({ ttsProvider: e.target.value })}>
              <option value="openrouter">OpenRouter</option>
              <option value="minimax">MiniMax</option>
              <option value="elevenlabs">ElevenLabs</option>
            </Select>
          </Field>
          <Field className="settings-voice-field" label={tr('基础 URL', 'Base URL')}>
            <Input value={form.ttsBaseUrl} onChange={(e) => updateForm({ ttsBaseUrl: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('模型', 'Model')}>
            <Input value={form.ttsModel} onChange={(e) => updateForm({ ttsModel: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('API 密钥', 'API Key')}>
            <Input
              type="password"
              value={form.ttsApiKey}
              onChange={(e) => updateForm({ ttsApiKey: e.target.value })}
              placeholder={config?.tts_api_key_configured ? keyText(true, config.tts_api_key_preview) : t('common.enterToSave')}
              autoComplete="off"
            />
          </Field>
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Mic size={18} />
            <h4>{tr('STT', 'STT')}</h4>
          </div>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            <Select value={form.sttProvider} onChange={(e) => updateForm({ sttProvider: e.target.value })}>
              <option value="whisper">{tr('Whisper 兼容', 'Whisper-compatible')}</option>
              <option value="minimax">MiniMax</option>
            </Select>
          </Field>
          <Field className="settings-voice-field" label={tr('基础 URL', 'Base URL')}>
            <Input value={form.sttBaseUrl} onChange={(e) => updateForm({ sttBaseUrl: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('模型', 'Model')}>
            <Input value={form.sttModel} onChange={(e) => updateForm({ sttModel: e.target.value })} />
          </Field>
          <label className="settings-checkbox-item settings-voice-check">
            <input
              type="checkbox"
              checked={form.sttUseTtsApiKey}
              onChange={(e) => updateForm({ sttUseTtsApiKey: e.target.checked })}
            />
            <span>{tr('复用 TTS API Key', 'Reuse TTS API key')}</span>
          </label>
          {!form.sttUseTtsApiKey && (
            <Field className="settings-voice-field" label={tr('STT API 密钥', 'STT API Key')}>
              <Input
                type="password"
                value={form.sttApiKey}
                onChange={(e) => updateForm({ sttApiKey: e.target.value })}
                placeholder={config?.stt_api_key_configured ? keyText(true, config.stt_api_key_preview) : t('common.enterToSave')}
                autoComplete="off"
              />
            </Field>
          )}
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Radio size={18} />
            <h4>{tr('实时语音', 'Realtime')}</h4>
          </div>
          <Field className="settings-voice-field" label={tr('Pipecat OpenAI 服务密钥', 'Pipecat OpenAI service key')}>
            <Input
              type="password"
              value={form.realtimeApiKey}
              onChange={(e) => updateForm({ realtimeApiKey: e.target.value })}
              placeholder={config?.realtime_effective_api_key_configured ? keyText(true, config.realtime_api_key_preview) : tr('填写 Pipecat OpenAI 服务 key', 'Enter a Pipecat OpenAI service key')}
              autoComplete="off"
            />
          </Field>
          <Field className="settings-voice-field" label={tr('实时模型', 'Realtime model')}>
            <Input value={form.realtimeModel} onChange={(e) => updateForm({ realtimeModel: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('实时声音', 'Realtime voice')}>
            <Input value={form.realtimeVoice} onChange={(e) => updateForm({ realtimeVoice: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('转写模型', 'Transcription Model')}>
            <Input value={form.realtimeTranscriptionModel} onChange={(e) => updateForm({ realtimeTranscriptionModel: e.target.value })} />
          </Field>
          <p className="settings-voice-note">
            {tr('实时语音通过 Pipecat 管道运行；逐轮语音继续使用 STT/TTS。', 'Realtime voice runs through Pipecat; turn-based voice keeps using STT/TTS.')}
          </p>
        </section>
      </div>

      <div className="settings-form-actions settings-voice-actions">
        <Button variant="secondary" onClick={loadConfig} disabled={loading || saving}>
          <RefreshCw size={14} />
          {tr('还原', 'Reset')}
        </Button>
        <Button variant="primary" onClick={handleSave} disabled={loading || saving}>
          <Save size={14} />
          {saving ? t('common.saving') : tr('保存并应用', 'Save and Apply')}
        </Button>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// SettingsPage
// ---------------------------------------------------------------------------

const SettingsPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const activeTab = SETTINGS_TAB_KEYS.includes(requestedTab as TabKey)
    ? requestedTab as TabKey
    : 'personas'

  return (
    <SettingsShell activeTab={activeTab}>
      {activeTab === 'personas' && <PersonasTab />}
      {activeTab === 'scenarios' && <ScenariosTab />}
      {activeTab === 'organizations' && <OrganizationsTab />}
      {activeTab === 'config' && <ConfigTab />}
    </SettingsShell>
  )
}

export default SettingsPage
