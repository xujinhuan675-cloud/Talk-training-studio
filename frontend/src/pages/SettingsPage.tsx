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
  SlidersHorizontal,
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
import { useI18n } from '../i18n'
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

type TabKey = 'personas' | 'scenarios' | 'organizations' | 'config' | 'preferences'
type SettingsTabKey = TabKey | 'training'

const TABS: { key: SettingsTabKey; labelZh: string; labelEn: string; icon: React.ReactNode }[] = [
  { key: 'personas', labelZh: '角色', labelEn: 'Personas', icon: <Users size={14} /> },
  { key: 'scenarios', labelZh: '场景', labelEn: 'Scenarios', icon: <Layers size={14} /> },
  { key: 'organizations', labelZh: '组织', labelEn: 'Organizations', icon: <Building2 size={14} /> },
  { key: 'training', labelZh: '训练管理', labelEn: 'Training', icon: <ClipboardList size={14} /> },
  { key: 'config', labelZh: '配置', labelEn: 'Config', icon: <KeyRound size={14} /> },
  { key: 'preferences', labelZh: '偏好', labelEn: 'Preferences', icon: <Volume2 size={14} /> },
]

const SETTINGS_TAB_KEYS: readonly TabKey[] = ['personas', 'scenarios', 'organizations', 'config', 'preferences']

export function SettingsShell({
  activeTab,
  children,
}: {
  activeTab: SettingsTabKey
  children: React.ReactNode
}) {
  const { tr } = useI18n()
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
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`settings-tab${activeTab === tab.key ? ' active' : ''}`}
            onClick={() => selectTab(tab.key)}
          >
            {tab.icon}
            {tr(tab.labelZh, tab.labelEn)}
          </button>
        ))}
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
  const { tr } = useI18n()
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
          <button
            className="persona-build-btn"
            onClick={() => navigate(APP_ROUTES.configPersonaNew)}
            title={tr('粘贴素材让 AI 生成对手画像', 'Paste materials for AI to generate opponent profiles')}
          >
            <Sparkles size={14} />
            {tr('从素材生成对手', 'Generate from Materials')}
          </button>
          <button className="settings-create-btn" onClick={startCreate}>
            <Plus size={14} />
            {tr('创建新角色', 'Create Persona')}
          </button>
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
              <Avatar name={p.name} color={p.avatar_color || '#2D9C6F'} size={40} />
            </div>
            <div className="settings-item-info">
              <div className="settings-item-name">{p.name}</div>
              <div className="settings-item-role">{p.role}</div>
            </div>
            <div className="settings-item-actions">
              <button
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); navigate(APP_ROUTES.configPersonaEdit(p.id)) }}
                title={tr('查看详情', 'View details')}
              >
                <Eye size={14} />
              </button>
              <button
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); startEdit(p) }}
                title={tr('编辑', 'Edit')}
              >
                <Pencil size={14} />
              </button>
              <button
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
                title={tr('删除', 'Delete')}
              >
                <Trash2 size={14} />
              </button>
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
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={tr('删除', 'Delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Scenarios Tab
// ---------------------------------------------------------------------------

function ScenariosTab() {
  const { tr } = useI18n()
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
      tr('删除场景', 'Delete Scenario'),
      tr('确定删除场景「{name}」？此操作无法撤销。', 'Delete scenario “{name}”? This cannot be undone.', { name: editing.name }),
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
        <h3 className="settings-section-title">{tr('场景', 'Scenarios')}</h3>
        <button className="settings-create-btn" onClick={startCreate}>
          <Plus size={14} />
          {tr('新建场景', 'New Scenario')}
        </button>
      </div>

      <div className="settings-list">
        {scenarios.length === 0 && !showForm && (
          <div className="settings-empty">
            <div className="settings-empty-icon">
              <Layers size={36} />
            </div>
            <p>{tr('暂无场景', 'No scenarios yet')}</p>
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
              <button
                className="settings-item-btn"
                onClick={(e) => { e.stopPropagation(); startEdit(s) }}
                title={tr('编辑', 'Edit')}
              >
                <Pencil size={14} />
              </button>
              <button
                className="settings-item-btn danger"
                onClick={(e) => {
                  e.stopPropagation()
                  dialog.ask(
                    tr('删除场景', 'Delete Scenario'),
                    tr('确定删除场景「{name}」？此操作无法撤销。', 'Delete scenario “{name}”? This cannot be undone.', { name: s.name }),
                    () => {
                    deleteScenario(s.id).then(() => { loadData(); reloadScenarios() })
                    },
                  )
                }}
                title={tr('删除', 'Delete')}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {showForm && (
        <div className="settings-form-panel">
          <h4>{isNew ? tr('新建场景', 'New Scenario') : tr('编辑场景', 'Edit Scenario')}</h4>

          <label className="field-label">
            {tr('名称', 'Name')}
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={tr('场景名称', 'Scenario name')}
              autoFocus
            />
          </label>

          <label className="field-label">
            {tr('描述（可选）', 'Description (optional)')}
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={tr('简短描述', 'Short description')}
            />
          </label>

          <label className="field-label">
            {tr('上下文提示词', 'Context Prompt')}
            <textarea
              value={contextPrompt}
              onChange={(e) => setContextPrompt(e.target.value)}
              placeholder={tr('设定场景的上下文提示词...', 'Set the context prompt for this scenario...')}
            />
          </label>

          <div className="field-label" style={{ marginBottom: 4 }}>{tr('推荐角色（可选）', 'Recommended Personas (optional)')}</div>
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
              <button className="btn-delete" onClick={handleDelete} disabled={submitting}>
                {tr('删除', 'Delete')}
              </button>
            )}
            <button className="btn-cancel" onClick={handleCancel}>{tr('取消', 'Cancel')}</button>
            <button
              className="btn-submit"
              onClick={handleSave}
              disabled={submitting}
            >
              {submitting ? tr('保存中...', 'Saving...') : tr('保存', 'Save')}
            </button>
          </div>
        </div>
      )}
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={tr('删除', 'Delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
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
  const { tr } = useI18n()
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

  return (
    <>
      <div className="settings-section-header">
        <h3 className="settings-section-title">{tr('组织', 'Organizations')}</h3>
        <button className="settings-create-btn" onClick={handleNewOrg}>
          <Plus size={14} />
          {tr('新建组织', 'New Organization')}
        </button>
      </div>

      <div className="settings-org-layout">
        {/* Org selector if multiple */}
        {orgs.length > 1 && (
          <select
            className="settings-org-selector"
            value={selectedOrg?.id ?? ''}
            onChange={(e) => e.target.value && loadOrgDetail(Number(e.target.value))}
          >
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
          </select>
        )}

        {/* Org sub-tabs */}
        <div className="settings-org-tabs">
          <button className={`settings-org-tab${orgTab === 'info' ? ' active' : ''}`} onClick={() => setOrgTab('info')}>
            {tr('基本信息', 'Basic Info')}
          </button>
          <button
            className={`settings-org-tab${orgTab === 'teams' ? ' active' : ''}`}
            onClick={() => setOrgTab('teams')}
            disabled={!selectedOrg}
          >
            {tr('团队', 'Teams')}
          </button>
          <button
            className={`settings-org-tab${orgTab === 'relationships' ? ' active' : ''}`}
            onClick={() => setOrgTab('relationships')}
            disabled={!selectedOrg}
          >
            {tr('角色关系', 'Persona Relationships')}
          </button>
        </div>

        <div className="settings-form-panel" style={{ marginTop: 0 }}>
          {orgTab === 'info' && (
            <>
              <label className="field-label">
                {tr('组织名称', 'Organization Name')}
                <input type="text" value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder={tr('如：Acme Corp', 'Example: Acme Corp')} />
              </label>
              <label className="field-label">
                {tr('行业', 'Industry')}
                <input type="text" value={orgIndustry} onChange={(e) => setOrgIndustry(e.target.value)} placeholder={tr('如：SaaS / 金融 / 制造', 'Example: SaaS / Finance / Manufacturing')} />
              </label>
              <label className="field-label">
                {tr('组织描述', 'Organization Description')}
                <textarea value={orgDescription} onChange={(e) => setOrgDescription(e.target.value)} placeholder={tr('组织的业务、产品、文化...', 'Business, products, culture...')} style={{ minHeight: 60 }} />
              </label>
              <label className="field-label">
                {tr('上下文提示词', 'Context Prompt')}
                <textarea value={orgContextPrompt} onChange={(e) => setOrgContextPrompt(e.target.value)} placeholder={tr('注入所有角色 system prompt 的组织背景...', 'Organization context injected into all persona system prompts...')} style={{ minHeight: 80 }} />
              </label>

              <div className="settings-form-actions">
                {selectedOrg && (
                  <button className="btn-delete" onClick={handleDeleteOrg}>{tr('删除组织', 'Delete Organization')}</button>
                )}
                <button className="btn-submit" onClick={handleSaveOrg} disabled={saving || !orgName.trim()}>
                  {saving ? tr('保存中...', 'Saving...') : tr('保存', 'Save')}
                </button>
              </div>
            </>
          )}

          {orgTab === 'teams' && selectedOrg && (
            <>
              {teams.length > 0 ? (
                <div className="team-list">
                  {teams.map((t) => {
                    const members = personas.filter((p) => p.team_id === t.id)
                    return (
                      <div key={t.id} className="team-item-block">
                        <div className="team-item">
                          <div className="team-item-info">
                            <div className="team-item-name">{t.name}</div>
                            {t.description && <div className="team-item-desc">{t.description}</div>}
                          </div>
                          <button className="team-delete-btn" onClick={() => handleDeleteTeam(t.id)}>{tr('删除', 'Delete')}</button>
                        </div>
                        <div className="team-members">
                          {members.length > 0 ? (
                            members.map((p) => (
                              <span key={p.id} className="team-member-chip">
                                <span className="team-member-dot" style={{ background: p.avatar_color || '#999' }} />
                                {p.name}
                                <button
                                  className="team-member-remove"
                                  onClick={() => handleRemoveFromTeam(p.id)}
                                  title={tr('移出团队', 'Remove from team')}
                                >&times;</button>
                              </span>
                            ))
                          ) : (
                            <span className="team-members-empty">{tr('暂无成员', 'No members')}</span>
                          )}
                          <select
                            className="team-add-member-select"
                            value=""
                            onChange={(e) => e.target.value && handleAssignToTeam(e.target.value, t.id)}
                          >
                            <option value="">{tr('+ 添加角色', '+ Add Persona')}</option>
                            {unassignedPersonas.map((p) => (
                              <option key={p.id} value={p.id}>{p.name} ({p.role})</option>
                            ))}
                          </select>
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
                <input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  placeholder={tr('团队名称', 'Team name')}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddTeam()}
                />
                <button onClick={handleAddTeam} disabled={!newTeamName.trim()}>{tr('添加团队', 'Add Team')}</button>
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
                      <button className="team-delete-btn" onClick={() => handleDeleteRelationship(r.id)}>{tr('删除', 'Delete')}</button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-hint">{tr('暂无角色关系', 'No persona relationships yet')}</div>
              )}
              <div className="add-rel-form">
                <select value={relFrom} onChange={(e) => setRelFrom(e.target.value)}>
                  <option value="">{tr('角色A', 'Persona A')}</option>
                  {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <select value={relType} onChange={(e) => setRelType(e.target.value)}>
                  <option value="superior">{tr('上级', 'Manager')}</option>
                  <option value="subordinate">{tr('下级', 'Direct Report')}</option>
                  <option value="peer">{tr('同级', 'Peer')}</option>
                  <option value="cross_department">{tr('跨部门', 'Cross-functional')}</option>
                </select>
                <select value={relTo} onChange={(e) => setRelTo(e.target.value)}>
                  <option value="">{tr('角色B', 'Persona B')}</option>
                  {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <input type="text" value={relDesc} onChange={(e) => setRelDesc(e.target.value)} placeholder={tr('描述（可选）', 'Description (optional)')} style={{ flex: 1 }} />
                <button onClick={handleAddRelationship} disabled={!relFrom || !relTo || relFrom === relTo}>{tr('添加', 'Add')}</button>
              </div>
            </>
          )}

          {error && <div className="settings-error">{error}</div>}
        </div>
      </div>
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={tr('删除', 'Delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
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
  realtimeCallUrl: string
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
  realtimeCallUrl: 'https://api.openai.com/v1/realtime/calls',
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
    realtimeCallUrl: config.realtime_call_url || DEFAULT_VOICE_FORM.realtimeCallUrl,
  }
}

function ConfigTab() {
  const { tr } = useI18n()
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
      : tr('未配置', 'Not configured')
  )

  const sourceText = (source: string) => {
    if (source === 'tts') return tr('复用 TTS key', 'Reuses TTS key')
    if (source === 'llm') return tr('回退到 LLM key', 'Falls back to LLM key')
    if (source === 'realtime') return tr('使用 Realtime 专用 key', 'Uses dedicated Realtime key')
    if (source === 'stt') return tr('使用 STT 专用 key', 'Uses dedicated STT key')
    return tr('未配置', 'Not configured')
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
        realtime_call_url: form.realtimeCallUrl,
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
        <h3 className="settings-section-title">{tr('AI 配置', 'AI Config')}</h3>
        <button className="settings-create-btn" onClick={loadConfig} disabled={loading || saving}>
          <RefreshCw size={14} />
          {loading ? tr('加载中...', 'Loading...') : tr('刷新', 'Refresh')}
        </button>
      </div>

      <div className="settings-voice-status">
        <div className="settings-voice-status-item">
          <KeyRound size={18} />
          <span>{tr('LLM', 'LLM')}</span>
          <strong>{config ? keyText(config.llm_api_key_configured, config.llm_api_key_preview) : tr('读取中', 'Reading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Volume2 size={18} />
          <span>{tr('TTS', 'TTS')}</span>
          <strong>{config ? keyText(config.tts_api_key_configured, config.tts_api_key_preview) : tr('读取中', 'Reading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Mic size={18} />
          <span>{tr('STT', 'STT')}</span>
          <strong>{config ? sourceText(config.stt_api_key_source) : tr('读取中', 'Reading')}</strong>
        </div>
        <div className="settings-voice-status-item">
          <Radio size={18} />
          <span>{tr('Realtime', 'Realtime')}</span>
          <strong>{config ? sourceText(config.realtime_api_key_source) : tr('读取中', 'Reading')}</strong>
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
            <h4>{tr('LLM 文本模型', 'LLM Text Model')}</h4>
          </div>
          <label className="field-label">
            {tr('Base URL', 'Base URL')}
            <input value={form.llmBaseUrl} onChange={(e) => updateForm({ llmBaseUrl: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('模型', 'Model')}
            <input value={form.llmDefaultModel} onChange={(e) => updateForm({ llmDefaultModel: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('调用模式', 'Wire API')}
            <select value={form.llmWireApi} onChange={(e) => updateForm({ llmWireApi: e.target.value })}>
              <option value="responses">Responses</option>
              <option value="chat_completions">Chat Completions</option>
            </select>
          </label>
          <label className="field-label">
            {tr('API Key', 'API Key')}
            <input
              type="password"
              value={form.llmApiKey}
              onChange={(e) => updateForm({ llmApiKey: e.target.value })}
              placeholder={config?.llm_api_key_configured ? keyText(true, config.llm_api_key_preview) : tr('填写后保存', 'Enter a key to save')}
              autoComplete="off"
            />
          </label>
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Volume2 size={18} />
            <h4>{tr('AI 语音回复 TTS', 'AI Speech Reply TTS')}</h4>
          </div>
          <label className="field-label">
            {tr('服务商', 'Provider')}
            <select value={form.ttsProvider} onChange={(e) => updateForm({ ttsProvider: e.target.value })}>
              <option value="openrouter">OpenRouter</option>
              <option value="minimax">MiniMax</option>
              <option value="elevenlabs">ElevenLabs</option>
            </select>
          </label>
          <label className="field-label">
            {tr('Base URL', 'Base URL')}
            <input value={form.ttsBaseUrl} onChange={(e) => updateForm({ ttsBaseUrl: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('模型', 'Model')}
            <input value={form.ttsModel} onChange={(e) => updateForm({ ttsModel: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('API Key', 'API Key')}
            <input
              type="password"
              value={form.ttsApiKey}
              onChange={(e) => updateForm({ ttsApiKey: e.target.value })}
              placeholder={config?.tts_api_key_configured ? keyText(true, config.tts_api_key_preview) : tr('填写后保存', 'Enter a key to save')}
              autoComplete="off"
            />
          </label>
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Mic size={18} />
            <h4>{tr('语音转写 STT', 'Speech Transcription STT')}</h4>
          </div>
          <label className="field-label">
            {tr('服务商', 'Provider')}
            <select value={form.sttProvider} onChange={(e) => updateForm({ sttProvider: e.target.value })}>
              <option value="whisper">Whisper-compatible</option>
              <option value="minimax">MiniMax</option>
            </select>
          </label>
          <label className="field-label">
            {tr('Base URL', 'Base URL')}
            <input value={form.sttBaseUrl} onChange={(e) => updateForm({ sttBaseUrl: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('模型', 'Model')}
            <input value={form.sttModel} onChange={(e) => updateForm({ sttModel: e.target.value })} />
          </label>
          <label className="settings-checkbox-item settings-voice-check">
            <input
              type="checkbox"
              checked={form.sttUseTtsApiKey}
              onChange={(e) => updateForm({ sttUseTtsApiKey: e.target.checked })}
            />
            <span>{tr('复用 TTS API Key', 'Reuse TTS API key')}</span>
          </label>
          {!form.sttUseTtsApiKey && (
            <label className="field-label">
              {tr('STT API Key', 'STT API Key')}
              <input
                type="password"
                value={form.sttApiKey}
                onChange={(e) => updateForm({ sttApiKey: e.target.value })}
                placeholder={config?.stt_api_key_configured ? keyText(true, config.stt_api_key_preview) : tr('填写后保存', 'Enter a key to save')}
                autoComplete="off"
              />
            </label>
          )}
        </section>

        <section className="settings-form-panel settings-voice-panel">
          <div className="settings-voice-panel-title">
            <Radio size={18} />
            <h4>{tr('实时 WebRTC 语音', 'Realtime WebRTC Voice')}</h4>
          </div>
          <label className="field-label">
            {tr('Realtime API Key', 'Realtime API Key')}
            <input
              type="password"
              value={form.realtimeApiKey}
              onChange={(e) => updateForm({ realtimeApiKey: e.target.value })}
              placeholder={config?.realtime_effective_api_key_configured ? keyText(true, config.realtime_api_key_preview) : tr('填写 OpenAI Realtime key', 'Enter an OpenAI Realtime key')}
              autoComplete="off"
            />
          </label>
          <label className="field-label">
            {tr('模型', 'Model')}
            <input value={form.realtimeModel} onChange={(e) => updateForm({ realtimeModel: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('声音', 'Voice')}
            <input value={form.realtimeVoice} onChange={(e) => updateForm({ realtimeVoice: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('转写模型', 'Transcription Model')}
            <input value={form.realtimeTranscriptionModel} onChange={(e) => updateForm({ realtimeTranscriptionModel: e.target.value })} />
          </label>
          <label className="field-label">
            {tr('Call URL', 'Call URL')}
            <input value={form.realtimeCallUrl} onChange={(e) => updateForm({ realtimeCallUrl: e.target.value })} />
          </label>
          <p className="settings-voice-note">
            {tr('Realtime WebRTC 目前使用 OpenAI Realtime 接口；OpenRouter 配置仅应用于逐轮 STT/TTS。', 'Realtime WebRTC currently uses the OpenAI Realtime API; OpenRouter settings apply to turn-based STT/TTS only.')}
          </p>
        </section>
      </div>

      <div className="settings-form-actions settings-voice-actions">
        <button className="btn-cancel" onClick={loadConfig} disabled={loading || saving}>
          <RefreshCw size={14} />
          {tr('还原', 'Reset')}
        </button>
        <button className="btn-submit" onClick={handleSave} disabled={loading || saving}>
          <Save size={14} />
          {saving ? tr('保存中...', 'Saving...') : tr('保存并应用', 'Save and Apply')}
        </button>
      </div>
    </>
  )
}

function PreferencesTab() {
  const { tr } = useI18n()

  return (
    <div className="settings-placeholder">
      <div className="settings-placeholder-icon">
        <SlidersHorizontal size={28} />
      </div>
      <h3>{tr('偏好稍后开放', 'Preferences coming later')}</h3>
      <p>{tr('模型、密钥和服务地址先在配置中管理。', 'Manage models, keys, and service URLs in Config for now.')}</p>
    </div>
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
      {activeTab === 'preferences' && <PreferencesTab />}
    </SettingsShell>
  )
}

export default SettingsPage
