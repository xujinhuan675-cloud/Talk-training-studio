import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
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
  RotateCcw,
  Save,
  KeyRound,
  ChevronRight,
  CheckCircle2,
  Clock3,
  AlertTriangle,
  Cable,
  Search,
  UserPlus,
  X,
} from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAppContext } from '../contexts/AppContext'
import { useAuthContext } from '../contexts/AuthContext'
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
import {
  LLM_PROVIDER_PRESETS,
  REALTIME_PROVIDER_PRESETS,
  STT_PROVIDER_PRESETS,
  TTS_PROVIDER_PRESETS,
  providerPresetByValue,
  type VoiceProviderPreset,
  type VoiceProviderStatus,
} from '../services/voiceProviderPresets'
import ConfirmDialog from '../components/layout/ConfirmDialog'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../components/ui/dialog'
import { Button } from '../components/ui/button'
import { Checkbox } from '../components/ui/checkbox'
import { Field, Input, Select, Textarea } from '../components/ui/form'
import { SegmentedControl } from '../components/ui/segmented-control'
import {
  fetchRealtimeCapabilities,
  type PipecatProviderCatalogChannelSummary,
  type PipecatProviderCatalogSummary,
  type RealtimeCapabilities,
} from '../services/trainingStudio'
import { useI18n, type TranslateInline, type TranslationKey } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import {
  assignNewApiTeamMember,
  fetchCurrentTeamMembers,
  searchNewApiTeamUsers,
  type AuthTeam,
  type AuthTeamMember,
} from '../services/auth'
import { getErrorMessage as getReadableErrorMessage } from '../utils/errors'
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
  return getReadableErrorMessage(error)
}

function personaDisplayKey(persona: PersonaSummary): string {
  return `${persona.name.trim().toLocaleLowerCase()}::${persona.role.trim().toLocaleLowerCase()}`
}

function dedupePersonasForDisplay(personas: PersonaSummary[]): PersonaSummary[] {
  const visibleByKey = new Map<string, PersonaSummary>()
  for (const persona of personas) {
    const key = personaDisplayKey(persona)
    const current = visibleByKey.get(key)
    if (!current || (!current.supports_v2 && persona.supports_v2)) {
      visibleByKey.set(key, persona)
    }
  }
  return Array.from(visibleByKey.values())
}

function matchesSearchQuery(values: Array<string | null | undefined>, query: string): boolean {
  const normalizedQuery = query.trim().toLocaleLowerCase()
  if (!normalizedQuery) return true
  return values.some((value) => value?.toLocaleLowerCase().includes(normalizedQuery))
}

type AudienceFilter = 'all' | 'sales' | 'customer_service' | 'management' | 'hr_interview' | 'negotiation' | 'general'
type BusinessAudienceFilter = Exclude<AudienceFilter, 'all'>

const AUDIENCE_FILTERS: readonly AudienceFilter[] = [
  'all',
  'sales',
  'customer_service',
  'management',
  'hr_interview',
  'negotiation',
  'general',
]

const BUSINESS_AUDIENCE_FILTERS: readonly BusinessAudienceFilter[] = [
  'sales',
  'customer_service',
  'management',
  'hr_interview',
  'negotiation',
  'general',
]

const BUSINESS_AUDIENCE_KEYWORDS: Record<BusinessAudienceFilter, readonly string[]> = {
  sales: [
    '销售',
    '售前',
    '客户经理',
    '客户拜访',
    '线索',
    '商机',
    '成交',
    '异议',
    'sales',
    'account executive',
    'business development',
    'prospect',
    'lead',
    'objection',
    'closing',
  ],
  customer_service: [
    '客服',
    '售后',
    '投诉',
    '工单',
    '客户成功',
    '服务',
    '续费',
    '退费',
    '满意度',
    'support',
    'customer service',
    'customer success',
    'complaint',
    'ticket',
    'refund',
  ],
  management: [
    '管理',
    '管理者',
    '经理',
    '主管',
    '团队',
    '下属',
    '直属',
    '绩效',
    '反馈',
    '辅导',
    '1:1',
    'leader',
    'manager',
    'performance',
    'feedback',
    'coaching',
  ],
  hr_interview: [
    'hr',
    '人力',
    '招聘',
    '面试',
    '候选人',
    '入职',
    'offer',
    'interview',
    'recruit',
    'hiring',
    'candidate',
  ],
  negotiation: [
    '谈判',
    '议价',
    '报价',
    '价格',
    '采购',
    '合同',
    '让步',
    '博弈',
    'negotiation',
    'negotiate',
    'price',
    'pricing',
    'procurement',
    'contract',
  ],
  general: [],
}

function inferBusinessAudienceValues(values: Array<string | null | undefined>): BusinessAudienceFilter[] {
  const text = values
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' ')
    .toLocaleLowerCase()

  // Short-term inference is centralized here so future explicit audience/use/department fields can replace it.
  const inferred = BUSINESS_AUDIENCE_FILTERS
    .filter((filter) => filter !== 'general')
    .filter((filter) => BUSINESS_AUDIENCE_KEYWORDS[filter].some((keyword) => text.includes(keyword.toLocaleLowerCase())))

  return inferred.length ? inferred : ['general']
}

function matchesAudienceFilter(values: Array<string | null | undefined>, filter: AudienceFilter): boolean {
  return filter === 'all' || inferBusinessAudienceValues(values).includes(filter)
}

function countAudienceFilters<T>(
  items: T[],
  valuesForItem: (item: T) => Array<string | null | undefined>,
): Record<AudienceFilter, number> {
  const counts = Object.fromEntries(AUDIENCE_FILTERS.map((filter) => [filter, 0])) as Record<AudienceFilter, number>
  counts.all = items.length

  items.forEach((item) => {
    inferBusinessAudienceValues(valuesForItem(item)).forEach((filter) => {
      counts[filter] += 1
    })
  })

  return counts
}

function personaAudienceValues(persona: PersonaSummary): Array<string | null | undefined> {
  return [persona.name, persona.role]
}

function scenarioAudienceValues(
  scenario: Scenario,
  personaLookup: Map<string, PersonaSummary>,
): Array<string | null | undefined> {
  return [
    scenario.name,
    scenario.description,
    scenario.context_prompt,
    ...scenario.suggested_persona_ids.flatMap((pid) => {
      const persona = personaLookup.get(pid)
      return persona ? [persona.name, persona.role] : [pid]
    }),
  ]
}

function audienceFilterLabel(filter: AudienceFilter, count: number, tr: TranslateInline): string {
  if (filter === 'all') return tr('全部类型', 'All types')
  if (filter === 'sales') return tr('销售 {count}', 'Sales {count}', { count })
  if (filter === 'customer_service') return tr('客服 {count}', 'Customer service {count}', { count })
  if (filter === 'management') return tr('管理者 {count}', 'Managers {count}', { count })
  if (filter === 'hr_interview') return tr('HR/面试 {count}', 'HR / Interview {count}', { count })
  if (filter === 'negotiation') return tr('谈判 {count}', 'Negotiation {count}', { count })
  return tr('通用 {count}', 'General {count}', { count })
}

type TabKey = 'personas' | 'scenarios' | 'members' | 'organizations' | 'config'
type SettingsTabKey = TabKey | 'training'

const TABS: { key: SettingsTabKey; labelKey: TranslationKey; icon: React.ReactNode }[] = [
  { key: 'personas', labelKey: 'settings.tabs.personas', icon: <Users size={14} /> },
  { key: 'scenarios', labelKey: 'settings.tabs.scenarios', icon: <Layers size={14} /> },
  { key: 'members', labelKey: 'settings.tabs.members', icon: <UserPlus size={14} /> },
  { key: 'organizations', labelKey: 'settings.tabs.organizations', icon: <Building2 size={14} /> },
  { key: 'training', labelKey: 'settings.tabs.training', icon: <ClipboardList size={14} /> },
  { key: 'config', labelKey: 'settings.tabs.config', icon: <KeyRound size={14} /> },
]

const SETTINGS_TAB_KEYS: readonly TabKey[] = ['personas', 'scenarios', 'members', 'organizations', 'config']
const PERSONAL_SETTINGS_TAB_KEYS: readonly TabKey[] = ['personas', 'scenarios', 'members']
const PERSONAL_SETTINGS_TABS = new Set<SettingsTabKey>(PERSONAL_SETTINGS_TAB_KEYS)

export function SettingsShell({
  activeTab,
  canUseManagementTabs,
  children,
}: {
  activeTab: SettingsTabKey
  canUseManagementTabs: boolean
  children: React.ReactNode
}) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const visibleTabs = TABS.filter((tab) => canUseManagementTabs || PERSONAL_SETTINGS_TABS.has(tab.key))

  const selectTab = (tab: SettingsTabKey) => {
    if (!canUseManagementTabs && !PERSONAL_SETTINGS_TABS.has(tab)) return
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
          options={visibleTabs.map((tab) => ({
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
  const dialog = useConfirmDialog()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<PersonaSummary | null>(null)
  const [personaQuery, setPersonaQuery] = useState('')
  const [personaAudience, setPersonaAudience] = useState<AudienceFilter>('all')

  const displayPersonas = useMemo(() => dedupePersonasForDisplay(Object.values(personaMap)), [personaMap])
  const personaAudienceCounts = useMemo(
    () => countAudienceFilters(displayPersonas, personaAudienceValues),
    [displayPersonas],
  )
  const visiblePersonas = useMemo(() => displayPersonas.filter((persona) => {
    const values = personaAudienceValues(persona)
    return matchesAudienceFilter(values, personaAudience) && matchesSearchQuery(values, personaQuery)
  }), [displayPersonas, personaAudience, personaQuery])
  const hasPersonaFilter = Boolean(personaQuery.trim()) || personaAudience !== 'all'
  const personaAudienceOptions = AUDIENCE_FILTERS.map((filter) => ({
    value: filter,
    label: audienceFilterLabel(filter, personaAudienceCounts[filter], tr),
  }))

  const startCreate = () => {
    setEditing(null)
    setDialogOpen(true)
  }

  const startEdit = (persona: PersonaSummary) => {
    setEditing(persona)
    setDialogOpen(true)
  }

  const openPersona = (persona: PersonaSummary) => {
    if (persona.supports_v2) {
      navigate(APP_ROUTES.configPersonaEdit(persona.id))
      return
    }
    startEdit(persona)
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
      <div className="settings-section-header actions-only">
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

      <div className="settings-form-panel settings-list-filter-panel">
        <h4>{tr('查找角色', 'Find personas')}</h4>
        <form className="settings-member-search-form settings-list-filter-form" onSubmit={(event) => event.preventDefault()}>
          <Input
            type="search"
            aria-label={tr('筛选角色', 'Filter personas')}
            value={personaQuery}
            onChange={(e) => setPersonaQuery(e.target.value)}
            placeholder={tr('筛选角色名称或定位', 'Filter persona name or role')}
          />
          <label className="settings-list-filter-select">
            <ClipboardList size={15} aria-hidden="true" />
            <Select
              aria-label={tr('角色适用对象', 'Persona audience')}
              value={personaAudience}
              onChange={(event) => setPersonaAudience(event.target.value as AudienceFilter)}
            >
              {personaAudienceOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <Button
            type="button"
            variant="secondary"
            disabled={!hasPersonaFilter}
            onClick={() => {
              setPersonaQuery('')
              setPersonaAudience('all')
            }}
          >
            <RotateCcw size={14} />
            {tr('重置', 'Reset')}
          </Button>
        </form>
      </div>

      <div className="settings-list">
        {visiblePersonas.length === 0 && (
          <div className="settings-empty">
            <div className="settings-empty-icon">
              <Users size={36} />
            </div>
            <p>{hasPersonaFilter ? tr('没有匹配的角色', 'No matching personas') : tr('暂无角色', 'No personas yet')}</p>
          </div>
        )}
        {visiblePersonas.map((p) => (
          <div
            key={p.id}
            className={`settings-list-item${editing?.id === p.id ? ' selected' : ''}`}
            onClick={() => openPersona(p)}
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
                onClick={(e) => { e.stopPropagation(); openPersona(p) }}
                title={p.supports_v2 ? tr('查看详情', 'View details') : tr('打开基础编辑', 'Open basic editor')}
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
  const [scenarioQuery, setScenarioQuery] = useState('')
  const [scenarioAudience, setScenarioAudience] = useState<AudienceFilter>('all')

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [contextPrompt, setContextPrompt] = useState('')
  const [suggestedPersonaIds, setSuggestedPersonaIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const showForm = isNew || editing !== null
  const scenarioPersonaLookup = useMemo(() => {
    const lookup = new Map<string, PersonaSummary>()
    Object.values(personaMap).forEach((persona) => lookup.set(persona.id, persona))
    allPersonas.forEach((persona) => lookup.set(persona.id, persona))
    return lookup
  }, [allPersonas, personaMap])
  const scenarioAudienceCounts = useMemo(
    () => countAudienceFilters(scenarios, (scenario) => scenarioAudienceValues(scenario, scenarioPersonaLookup)),
    [scenarioPersonaLookup, scenarios],
  )
  const visibleScenarios = useMemo(() => scenarios.filter((scenario) => {
    const values = scenarioAudienceValues(scenario, scenarioPersonaLookup)
    return matchesAudienceFilter(values, scenarioAudience) && matchesSearchQuery(values, scenarioQuery)
  }), [scenarioAudience, scenarioPersonaLookup, scenarioQuery, scenarios])
  const hasScenarioFilter = Boolean(scenarioQuery.trim()) || scenarioAudience !== 'all'
  const scenarioAudienceOptions = AUDIENCE_FILTERS.map((filter) => ({
    value: filter,
    label: audienceFilterLabel(filter, scenarioAudienceCounts[filter], tr),
  }))

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
      <div className="settings-section-header actions-only">
        <div className="settings-header-actions">
          <Button className="settings-create-btn" variant="primary" onClick={startCreate}>
            <Plus size={14} />
            {tr('新建对话场景', 'New room scenario')}
          </Button>
        </div>
      </div>

      <div className="settings-form-panel settings-list-filter-panel">
        <h4>{tr('查找对话场景', 'Find room scenarios')}</h4>
        <form className="settings-member-search-form settings-list-filter-form" onSubmit={(event) => event.preventDefault()}>
          <Input
            type="search"
            aria-label={tr('筛选对话场景', 'Filter room scenarios')}
            value={scenarioQuery}
            onChange={(e) => setScenarioQuery(e.target.value)}
            placeholder={tr('筛选场景名称、描述或角色', 'Filter scenario name, description, or persona')}
          />
          <label className="settings-list-filter-select">
            <Layers size={15} aria-hidden="true" />
            <Select
              aria-label={tr('对话场景适用对象', 'Room scenario audience')}
              value={scenarioAudience}
              onChange={(event) => setScenarioAudience(event.target.value as AudienceFilter)}
            >
              {scenarioAudienceOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <Button
            type="button"
            variant="secondary"
            disabled={!hasScenarioFilter}
            onClick={() => {
              setScenarioQuery('')
              setScenarioAudience('all')
            }}
          >
            <RotateCcw size={14} />
            {tr('重置', 'Reset')}
          </Button>
        </form>
      </div>

      <div className="settings-list">
        {visibleScenarios.length === 0 && (
          <div className="settings-empty">
            <div className="settings-empty-icon">
              <Layers size={36} />
            </div>
            <p>{hasScenarioFilter ? tr('没有匹配的对话场景', 'No matching room scenarios') : tr('暂无对话场景', 'No room scenarios yet')}</p>
          </div>
        )}
        {visibleScenarios.map((s) => (
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

      <Dialog open={showForm} onOpenChange={(open) => { if (!open) handleCancel() }}>
        <DialogContent className="settings-scenario-dialog" aria-describedby={undefined}>
          <div className="settings-scenario-dialog-title">
            <DialogTitle className="settings-scenario-dialog-heading">
              {isNew ? tr('新建对话场景', 'New room scenario') : tr('编辑对话场景', 'Edit room scenario')}
            </DialogTitle>
            <Button
              className="settings-scenario-dialog-close"
              variant="ghost"
              size="icon"
              onClick={handleCancel}
              title={tr('关闭', 'Close')}
              aria-label={tr('关闭', 'Close')}
            >
              <X size={16} />
            </Button>
          </div>

          <div className="settings-scenario-dialog-body">
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

            <div className="field-label settings-linked-personas-label">{tr('关联角色', 'Linked Personas')}</div>
            <div className="settings-checkbox-list">
              {allPersonas.map((p) => (
                <label key={p.id} className="settings-checkbox-item">
                  <Checkbox
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
          </div>

          <div className="settings-form-actions settings-scenario-dialog-actions">
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
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={dialog.open} title={dialog.title} message={dialog.message} confirmLabel={t('common.delete')} danger onConfirm={dialog.confirm} onCancel={dialog.close} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Team Members Tab
// ---------------------------------------------------------------------------

function formatMemberNumber(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return new Intl.NumberFormat().format(value)
}

function teamMemberDisplayName(member: AuthTeamMember): string {
  return member.displayName?.trim() || member.username || `User #${member.userId}`
}

function teamMemberAvatarColor(member: AuthTeamMember): string {
  if (member.isAdmin) return '#2563EB'
  return '#64748B'
}

function TeamMemberRow({
  member,
  action,
}: {
  member: AuthTeamMember
  action?: React.ReactNode
}) {
  const { tr } = useI18n()
  const displayName = teamMemberDisplayName(member)
  const subtitle = member.email || (member.displayName && member.username !== member.displayName ? member.username : '')
  const quotaRemaining = formatMemberNumber(member.quotaRemaining)
  const quotaUsed = formatMemberNumber(member.quotaUsed)
  const requestCount = formatMemberNumber(member.requestCount)

  return (
    <div className="settings-list-item settings-member-row">
      <div className="settings-item-avatar">
        <Avatar name={displayName} color={teamMemberAvatarColor(member)} size={40} />
      </div>
      <div className="settings-item-info settings-member-info">
        <div className="settings-item-name">{displayName}</div>
        {subtitle && <div className="settings-item-role">{subtitle}</div>}
        <div className="settings-member-chips">
          <span className="settings-member-chip">
            {member.isAdmin ? tr('管理员', 'Administrator') : tr('成员', 'Member')}
          </span>
          {member.group && (
            <span className="settings-member-chip">{tr('组 {group}', 'Group {group}', { group: member.group })}</span>
          )}
          {quotaRemaining && (
            <span className="settings-member-chip">{tr('余额 {count}', 'Balance {count}', { count: quotaRemaining })}</span>
          )}
          {quotaUsed && (
            <span className="settings-member-chip">{tr('已用 {count}', 'Used {count}', { count: quotaUsed })}</span>
          )}
          {requestCount && (
            <span className="settings-member-chip">{tr('请求 {count}', 'Requests {count}', { count: requestCount })}</span>
          )}
        </div>
      </div>
      {action && <div className="settings-member-actions">{action}</div>}
    </div>
  )
}

function TeamMembersTab() {
  const { t, tr } = useI18n()
  const { currentUser, isAdmin, refreshSession } = useAuthContext()
  const isNewApiSession = currentUser?.authProvider === 'newapi'
  const canManageMembers = isNewApiSession && isAdmin

  const [team, setTeam] = useState<AuthTeam | null>(null)
  const [members, setMembers] = useState<AuthTeamMember[]>([])
  const [totalMembers, setTotalMembers] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<AuthTeamMember[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [assigningUserId, setAssigningUserId] = useState<number | null>(null)

  const loadMembers = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      if (!isNewApiSession) {
        setTeam(null)
        setMembers([])
        setTotalMembers(0)
        return
      }
      const payload = await fetchCurrentTeamMembers()
      setTeam(payload.team)
      setMembers(payload.members)
      setTotalMembers(payload.total)
    } catch (err) {
      setTeam(null)
      setMembers([])
      setTotalMembers(0)
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [isNewApiSession])

  useEffect(() => {
    void loadMembers()
  }, [loadMembers])

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const keyword = searchKeyword.trim()
    setSearchError(null)
    setNotice(null)
    setHasSearched(Boolean(keyword))
    if (!keyword) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const payload = await searchNewApiTeamUsers(keyword, 20)
      setTeam(payload.team)
      setSearchResults(payload.users)
    } catch (err) {
      setSearchResults([])
      setSearchError(getErrorMessage(err))
    } finally {
      setSearching(false)
    }
  }

  const handleAssign = async (userId: number) => {
    setAssigningUserId(userId)
    setSearchError(null)
    setNotice(null)
    try {
      const assigned = await assignNewApiTeamMember(userId)
      setSearchResults((current) =>
        current.map((member) =>
          member.userId === userId
            ? {
                ...member,
                group: assigned.group,
                teamId: assigned.teamId,
                teamName: assigned.teamName,
                inTeam: true,
              }
            : member,
        ),
      )
      await loadMembers()
      await refreshSession().catch(() => undefined)
      setNotice(tr('成员已加入当前团队。', 'Member added to the current team.'))
    } catch (err) {
      setSearchError(getErrorMessage(err))
    } finally {
      setAssigningUserId(null)
    }
  }

  const teamName = team?.name || currentUser?.teamName || tr('当前团队', 'Current team')
  const groupName = team?.group || currentUser?.newapiGroup || ''
  const memberCount = totalMembers || members.length

  if (!isNewApiSession) {
    return (
      <>
        <div className="settings-empty">
          <div className="settings-empty-icon">
            <Users size={36} />
          </div>
          <p>{tr('请登录后查看团队成员。', 'Sign in to view team members.')}</p>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="settings-section-header actions-only">
        <div className="settings-header-actions">
          <Button className="settings-header-button" variant="secondary" onClick={loadMembers} disabled={loading}>
            <RefreshCw size={14} />
            {t('common.refresh')}
          </Button>
        </div>
      </div>

      <div className="settings-members-summary">
        <div className="settings-members-summary-main">
          <span className="settings-members-summary-label">{tr('当前团队', 'Current team')}</span>
          <strong>{teamName}</strong>
          {groupName && <span className="settings-members-summary-group">{tr('组 {group}', 'Group {group}', { group: groupName })}</span>}
        </div>
        <div className="settings-members-stat">
          <span>{tr('成员数', 'Members')}</span>
          <strong>{memberCount}</strong>
        </div>
      </div>

      {notice && <div className="settings-success">{notice}</div>}
      {error && <div className="settings-error">{error}</div>}

      {canManageMembers && (
        <div className="settings-form-panel settings-member-search-panel">
          <h4>{tr('添加成员', 'Add member')}</h4>
          <form className="settings-member-search-form" onSubmit={handleSearch}>
            <Input
              type="search"
              value={searchKeyword}
              onChange={(event) => {
                setSearchKeyword(event.target.value)
                setSearchError(null)
              }}
              placeholder={tr('搜索用户名或邮箱', 'Search username or email')}
            />
            <Button variant="primary" type="submit" disabled={searching || !searchKeyword.trim()}>
              <Search size={14} />
              {searching ? t('common.loading') : tr('搜索', 'Search')}
            </Button>
          </form>
          {searchError && <div className="settings-error">{searchError}</div>}
          <div className="settings-member-search-results">
            {searchResults.map((member) => (
              <TeamMemberRow
                key={member.userId}
                member={member}
                action={
                  <Button
                    variant={member.inTeam ? 'secondary' : 'primary'}
                    size="sm"
                    disabled={member.inTeam || assigningUserId !== null}
                    onClick={() => handleAssign(member.userId)}
                  >
                    <UserPlus size={14} />
                    {member.inTeam
                      ? tr('已在团队', 'In team')
                      : assigningUserId === member.userId
                        ? t('common.saving')
                        : tr('加入', 'Add')}
                  </Button>
                }
              />
            ))}
            {hasSearched && !searching && searchResults.length === 0 && !searchError && (
              <div className="settings-empty settings-member-search-empty">
                <p>{tr('没有找到可添加的用户。', 'No matching users found.')}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="settings-empty">
          <div className="settings-empty-icon">
            <Users size={36} />
          </div>
          <p>{t('common.loading')}</p>
        </div>
      ) : (
        <div className="settings-list">
          {members.length === 0 && !error && (
            <div className="settings-empty">
              <div className="settings-empty-icon">
                <Users size={36} />
              </div>
              <p>{tr('当前团队暂无成员。', 'No members in the current team yet.')}</p>
            </div>
          )}
          {members.map((member) => (
            <TeamMemberRow key={member.userId} member={member} />
          ))}
        </div>
      )}
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
  const [orgTabHint, setOrgTabHint] = useState<string | null>(null)

  const loadOrgs = () => fetchOrganizations().then(setOrgs).catch(() => {})

  const orgSaveHint = tr(
    '先保存组织基础信息，才能配置团队和角色关系。',
    'Save the organization basics before configuring teams and relationships.',
  )

  const loadOrgDetail = useCallback(async (orgId: number) => {
    const detail = await fetchOrganizationDetail(orgId)
    setSelectedOrg(detail.organization)
    setTeams(detail.teams)
    setOrgName(detail.organization.name)
    setOrgIndustry(detail.organization.industry)
    setOrgDescription(detail.organization.description)
    setOrgContextPrompt(detail.organization.context_prompt)
    setOrgTabHint(null)
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
    setOrgTabHint(null)
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
      setOrgTabHint(null)
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
        setOrgTab('info')
        setOrgTabHint(null)
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
    { value: 'teams' as const, label: tr('团队', 'Teams'), title: selectedOrg ? undefined : orgSaveHint },
    { value: 'relationships' as const, label: tr('关系', 'Relationships'), title: selectedOrg ? undefined : orgSaveHint },
  ]
  const handleOrgTabChange = (value: typeof orgTab) => {
    if (!selectedOrg && value !== 'info') {
      setOrgTabHint(orgSaveHint)
      setOrgTab('info')
      return
    }
    setOrgTabHint(null)
    setOrgTab(value)
  }

  return (
    <>
      <div className="settings-section-header actions-only">
        <div className="settings-header-actions">
          <Button className="settings-create-btn" variant="primary" onClick={handleNewOrg}>
            <Plus size={14} />
            {tr('新建组织', 'New Organization')}
          </Button>
        </div>
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
          onValueChange={handleOrgTabChange}
        />

        {!selectedOrg && (
          <div className="settings-warning settings-org-save-hint" role={orgTabHint ? 'alert' : 'status'}>
            <AlertTriangle size={14} />
            <span>
              {orgTabHint ?? tr(
                '保存组织后可以继续配置团队和角色关系。',
                'After saving this organization, you can configure teams and relationships.',
              )}
            </span>
          </div>
        )}

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
  llmProvider: string
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
  realtimeProvider: string
  realtimeBaseUrl: string
  realtimeApiKey: string
  realtimeModel: string
  realtimeVoice: string
  realtimeTranscriptionModel: string
}

const DEFAULT_VOICE_FORM: VoicePreferenceForm = {
  llmProvider: 'flowguide',
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
  realtimeProvider: 'openai',
  realtimeBaseUrl: 'https://api.openai.com/v1/realtime/calls',
  realtimeApiKey: '',
  realtimeModel: 'gpt-realtime-2.1',
  realtimeVoice: 'marin',
  realtimeTranscriptionModel: 'gpt-realtime-whisper',
}

function toVoiceForm(config: VoicePreferenceConfig): VoicePreferenceForm {
  return {
    llmProvider: config.llm_provider || DEFAULT_VOICE_FORM.llmProvider,
    llmBaseUrl: config.llm_base_url ?? DEFAULT_VOICE_FORM.llmBaseUrl,
    llmDefaultModel: config.llm_default_model || DEFAULT_VOICE_FORM.llmDefaultModel,
    llmWireApi: config.llm_wire_api || DEFAULT_VOICE_FORM.llmWireApi,
    llmApiKey: '',
    ttsProvider: config.tts_provider || DEFAULT_VOICE_FORM.ttsProvider,
    ttsBaseUrl: config.tts_base_url ?? DEFAULT_VOICE_FORM.ttsBaseUrl,
    ttsModel: config.tts_model || DEFAULT_VOICE_FORM.ttsModel,
    ttsApiKey: '',
    sttProvider: config.stt_provider || DEFAULT_VOICE_FORM.sttProvider,
    sttBaseUrl: config.stt_base_url ?? DEFAULT_VOICE_FORM.sttBaseUrl,
    sttModel: config.stt_model || DEFAULT_VOICE_FORM.sttModel,
    sttUseTtsApiKey: config.stt_use_tts_api_key,
    sttApiKey: '',
    realtimeProvider: config.realtime_provider || DEFAULT_VOICE_FORM.realtimeProvider,
    realtimeBaseUrl: config.realtime_base_url ?? DEFAULT_VOICE_FORM.realtimeBaseUrl,
    realtimeApiKey: '',
    realtimeModel: config.realtime_model || DEFAULT_VOICE_FORM.realtimeModel,
    realtimeVoice: config.realtime_voice || DEFAULT_VOICE_FORM.realtimeVoice,
    realtimeTranscriptionModel: config.realtime_transcription_model || DEFAULT_VOICE_FORM.realtimeTranscriptionModel,
  }
}

type VoiceModuleKey = 'llm' | 'stt' | 'tts' | 'realtime' | 'transport'
type VoiceModuleTone = 'ready' | 'warning' | 'blocked' | 'neutral'

interface VoiceProviderOption {
  value: string
  label: string
  status: VoiceProviderStatus
  disabled?: boolean
}

function providerOptionsFromPresets(presets: VoiceProviderPreset[]): VoiceProviderOption[] {
  return presets.map((preset) => ({
    value: preset.value,
    label: preset.label,
    status: preset.status,
  }))
}

const BUILT_IN_LLM_PROVIDERS = providerOptionsFromPresets(LLM_PROVIDER_PRESETS)
const BUILT_IN_TTS_PROVIDERS = providerOptionsFromPresets(TTS_PROVIDER_PRESETS)
const BUILT_IN_STT_PROVIDERS = providerOptionsFromPresets(STT_PROVIDER_PRESETS)
const BUILT_IN_REALTIME_PROVIDERS = providerOptionsFromPresets(REALTIME_PROVIDER_PRESETS)

function titleCaseProvider(value: string): string {
  const known: Record<string, string> = {
    openai: 'OpenAI',
    flowguide: 'FlowGuide gateway',
    openrouter: 'OpenRouter',
    minimax: 'MiniMax',
    elevenlabs: 'ElevenLabs',
    assemblyai: 'AssemblyAI',
    anthropic: 'Anthropic',
    cartesia: 'Cartesia',
    cerebras: 'Cerebras',
    deepgram: 'Deepgram',
    deepseek: 'DeepSeek',
    whisper: 'Whisper compatible',
    google: 'Google',
    azure: 'Azure',
    aws: 'AWS',
    groq: 'Groq',
    hume: 'Hume',
    lmnt: 'LMNT',
    mistral: 'Mistral',
    ollama: 'Ollama',
    perplexity: 'Perplexity',
    qwen: 'Qwen',
    rime: 'Rime',
    soniox: 'Soniox',
    speechmatics: 'Speechmatics',
    together: 'Together AI',
    xai: 'xAI',
    websocket: 'WebSocket',
    silero: 'Silero',
  }
  if (known[value]) return known[value]
  return value
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => known[part] ?? `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ')
}

function providerCatalogChannel(
  catalog: PipecatProviderCatalogSummary | null | undefined,
  channel: string,
): PipecatProviderCatalogChannelSummary | null {
  return catalog?.channels?.[channel] ?? null
}

function providerOptionsFromCatalog(
  channel: PipecatProviderCatalogChannelSummary | null,
  runtimeProviders: VoiceProviderOption[],
): VoiceProviderOption[] {
  const optionAliases = (value: string): string[] => {
    if (value === 'openai') return ['openai', 'openai.realtime', 'openai_realtime']
    return [value]
  }
  const runtimeValues = new Set(runtimeProviders.flatMap((option) => optionAliases(option.value)))
  const pipecatOptions = Array.from(new Set(channel?.runtimeIntegrated ?? []))
    .filter((provider) => !runtimeValues.has(provider))
    .sort((a, b) => a.localeCompare(b))
    .map((provider): VoiceProviderOption => ({
      value: provider,
      label: titleCaseProvider(provider),
      status: 'pipecat',
      disabled: true,
    }))
  const knownValues = new Set([...runtimeValues, ...pipecatOptions.map((option) => option.value)])
  const inventoryOptions = Array.from(new Set(channel?.inventoryOnly ?? []))
    .filter((provider) => !knownValues.has(provider))
    .sort((a, b) => a.localeCompare(b))
    .map((provider): VoiceProviderOption => ({
      value: provider,
      label: titleCaseProvider(provider),
      status: 'inventory',
      disabled: true,
    }))
  return [...pipecatOptions, ...inventoryOptions]
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timer: number | undefined
  const timeout = new Promise<never>((_, reject) => {
    timer = window.setTimeout(() => reject(new Error(message)), timeoutMs)
  })
  return Promise.race([promise, timeout]).finally(() => {
    if (timer !== undefined) window.clearTimeout(timer)
  })
}

function ConfigTab() {
  const { t, tr } = useI18n()
  const [config, setConfig] = useState<VoicePreferenceConfig | null>(null)
  const [realtimeCapabilities, setRealtimeCapabilities] = useState<RealtimeCapabilities | null>(null)
  const [form, setForm] = useState<VoicePreferenceForm>(DEFAULT_VOICE_FORM)
  const [loading, setLoading] = useState(true)
  const [, setCatalogLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [activeModule, setActiveModule] = useState<VoiceModuleKey | null>(null)

  const updateForm = (patch: Partial<VoicePreferenceForm>) => {
    setForm((current) => ({ ...current, ...patch }))
  }

  const loadProviderCatalog = useCallback(async () => {
    setCatalogLoading(true)
    setCatalogError(null)
    try {
      const next = await withTimeout(
        fetchRealtimeCapabilities(),
        8000,
        tr('Pipecat provider catalog 请求超时', 'Pipecat provider catalog request timed out'),
      )
      setRealtimeCapabilities(next)
    } catch (err) {
      setRealtimeCapabilities(null)
      setCatalogError(getErrorMessage(err))
    } finally {
      setCatalogLoading(false)
    }
  }, [tr])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setNotice(null)
    setCatalogError(null)
    try {
      const next = await fetchVoiceConfig()
      setConfig(next)
      setForm(toVoiceForm(next))
    } catch (err) {
      setNotice({ tone: 'error', text: getErrorMessage(err) })
    } finally {
      setLoading(false)
    }
    void loadProviderCatalog()
  }, [loadProviderCatalog])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const keyText = (configured: boolean, preview: string | null) => (
    configured
      ? tr('已配置 {preview}', 'Configured {preview}', { preview: preview || '' })
      : t('common.notConfigured')
  )

  const handleSave = async () => {
    setSaving(true)
    setNotice(null)
    try {
      const payload = {
        llm_provider: form.llmProvider,
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
        realtime_provider: form.realtimeProvider,
        realtime_base_url: form.realtimeBaseUrl,
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

  const catalog = realtimeCapabilities?.pipecat.providerCatalogSummary ?? null
  const sttChannel = providerCatalogChannel(catalog, 'stt')
  const ttsChannel = providerCatalogChannel(catalog, 'tts')
  const llmChannel = providerCatalogChannel(catalog, 'llm')
  const realtimeChannel = providerCatalogChannel(catalog, 'realtime')
  const transportChannel = providerCatalogChannel(catalog, 'transport')
  const vadChannel = providerCatalogChannel(catalog, 'vad')
  const turnChannel = providerCatalogChannel(catalog, 'turn_detection')

  const llmProviderOptions = [
    ...BUILT_IN_LLM_PROVIDERS,
    ...providerOptionsFromCatalog(llmChannel, BUILT_IN_LLM_PROVIDERS),
  ]
  const ttsProviderOptions = [
    ...BUILT_IN_TTS_PROVIDERS,
    ...providerOptionsFromCatalog(ttsChannel, BUILT_IN_TTS_PROVIDERS),
  ]
  const sttProviderOptions = [
    ...BUILT_IN_STT_PROVIDERS,
    ...providerOptionsFromCatalog(sttChannel, BUILT_IN_STT_PROVIDERS),
  ]
  const realtimeProviderOptions = [
    ...BUILT_IN_REALTIME_PROVIDERS,
    ...providerOptionsFromCatalog(realtimeChannel, BUILT_IN_REALTIME_PROVIDERS),
  ]

  const applyLlmProvider = (provider: string) => {
    const preset = providerPresetByValue('llm', provider)
    if (!preset) return
    updateForm({
      llmProvider: provider,
      llmBaseUrl: preset.baseUrl,
      llmDefaultModel: preset.model,
      llmWireApi: preset.wireApi || DEFAULT_VOICE_FORM.llmWireApi,
    })
  }

  const applyTtsProvider = (provider: string) => {
    const preset = providerPresetByValue('tts', provider)
    if (!preset) return
    updateForm({
      ttsProvider: provider,
      ttsBaseUrl: preset.baseUrl,
      ttsModel: preset.model,
    })
  }

  const applySttProvider = (provider: string) => {
    const preset = providerPresetByValue('stt', provider)
    if (!preset) return
    updateForm({
      sttProvider: provider,
      sttBaseUrl: preset.baseUrl,
      sttModel: preset.model,
      sttUseTtsApiKey: Boolean(preset.reuseTtsKey),
    })
  }

  const applyRealtimeProvider = (provider: string) => {
    const preset = providerPresetByValue('realtime', provider)
    if (!preset) return
    updateForm({
      realtimeProvider: provider,
      realtimeBaseUrl: preset.baseUrl,
      realtimeModel: preset.model,
      realtimeVoice: preset.realtimeVoice || form.realtimeVoice,
      realtimeTranscriptionModel: preset.realtimeTranscriptionModel || form.realtimeTranscriptionModel,
    })
  }

  const toneLabel = (tone: VoiceModuleTone) => {
    if (tone === 'neutral') return tr('待接入', 'Adapter pending')
    if (tone === 'ready') return tr('可用', 'Ready')
    if (tone === 'warning') return tr('需配置', 'Needs config')
    if (tone === 'blocked') return tr('未接入', 'Not wired')
    return tr('只读', 'Read-only')
  }

  const toneForProvider = (
    provider: string,
    channel: 'llm' | 'stt' | 'tts' | 'realtime',
    configured: boolean,
  ): VoiceModuleTone => {
    const preset = providerPresetByValue(channel, provider)
    if (preset?.status === 'inventory') return 'neutral'
    if (preset && preset.status !== 'runtime') return 'blocked'
    return configured ? 'ready' : 'warning'
  }

  const realtimeModuleTone = (): VoiceModuleTone => {
    const preset = providerPresetByValue('realtime', form.realtimeProvider)
    if (preset?.status === 'inventory') return 'neutral'
    if (form.realtimeProvider === 'openai') {
      if (realtimeCapabilities?.pipecat.readyForCall) return 'ready'
      return config?.realtime_effective_api_key_configured ? 'warning' : 'blocked'
    }
    if (form.realtimeProvider === 'volcengine.doubao_realtime') {
      const volcengineRealtime = realtimeCapabilities?.volcengineDoubaoRealtime
        ?? realtimeCapabilities?.providers?.['volcengine.doubao_realtime']
      if (volcengineRealtime?.readyForCall) return 'ready'
      return config?.realtime_effective_api_key_configured ? 'warning' : 'blocked'
    }
    return toneForProvider(
      form.realtimeProvider,
      'realtime',
      Boolean(config?.realtime_effective_api_key_configured),
    )
  }

  const voiceModules: Array<{
    key: VoiceModuleKey
    icon: React.ReactNode
    title: string
    subtitle: string
    model: string
    tone: VoiceModuleTone
  }> = [
    {
      key: 'llm',
      icon: <KeyRound size={18} />,
      title: tr('LLM 回复生成', 'LLM response generation'),
      subtitle: tr('组合语音和实时语音都会用到的回复模型', 'Response model used by turn-based and realtime voice'),
      model: form.llmDefaultModel,
      tone: toneForProvider(form.llmProvider, 'llm', Boolean(config?.llm_api_key_configured)),
    },
    {
      key: 'stt',
      icon: <Mic size={18} />,
      title: tr('STT 语音识别', 'STT speech recognition'),
      subtitle: tr('回合制语音的录音转文字模块', 'Recording-to-text module for turn-based voice'),
      model: form.sttModel,
      tone: toneForProvider(form.sttProvider, 'stt', Boolean(config && config.stt_api_key_source !== 'missing')),
    },
    {
      key: 'tts',
      icon: <Volume2 size={18} />,
      title: tr('TTS 语音合成', 'TTS speech synthesis'),
      subtitle: tr('回合制语音的文字转语音模块', 'Text-to-speech module for turn-based voice'),
      model: form.ttsModel,
      tone: toneForProvider(
        form.ttsProvider,
        'tts',
        config?.tts_runtime_available ?? Boolean(config?.tts_api_key_configured),
      ),
    },
    {
      key: 'realtime',
      icon: <Radio size={18} />,
      title: tr('Realtime 实时语音', 'Realtime voice'),
      subtitle: tr('连续音频、打断、实时输出的运行链路；非 runtime provider 保持待接入状态', 'Runtime path for continuous audio, interruption, and realtime output; non-runtime providers stay adapter pending'),
      model: form.realtimeModel,
      tone: realtimeModuleTone(),
    },
    {
      key: 'transport',
      icon: <Cable size={18} />,
      title: tr('Transport / VAD / Turn', 'Transport / VAD / Turn'),
      subtitle: tr('实时链路的传输、端点检测和回合判断', 'Transport, voice activity detection, and turn detection for realtime voice'),
      model: tr('固定运行组件', 'Fixed runtime components'),
      tone: realtimeCapabilities?.pipecat.websocketAvailable && realtimeCapabilities?.pipecat.vadAvailable && realtimeCapabilities?.pipecat.turnDetectionAvailable ? 'ready' : 'warning',
    },
  ]

  const activeModuleMeta = voiceModules.find((module) => module.key === activeModule) ?? null

  const renderProviderSelect = (
    value: string,
    options: VoiceProviderOption[],
    onChange: (value: string) => void,
  ) => (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <option key={`${option.status}:${option.value}`} value={option.value} disabled={option.disabled}>
          {option.label}
          {option.status === 'pipecat' ? ` - ${tr('Pipecat runtime', 'Pipecat runtime')}` : ''}
          {option.status === 'inventory' ? ` - ${tr('待接入', 'Adapter pending')}` : ''}
        </option>
      ))}
    </Select>
  )

  const renderCatalogSummary = (channel: PipecatProviderCatalogChannelSummary | null, label: string) => {
    if (!channel) {
      return (
        <div className="settings-voice-catalog-row">
          <span>{label}</span>
          <strong>{tr('未加载', 'Not loaded')}</strong>
        </div>
      )
    }
    return (
      <div className="settings-voice-catalog-row">
        <span>{label}</span>
        <strong>
          {tr('{runtime} 已接入 / {inventory} 待接入', '{runtime} wired / {inventory} inventory', {
            runtime: String(channel.runtimeIntegrated.length),
            inventory: String(channel.inventoryOnly.length),
          })}
        </strong>
      </div>
    )
  }

  const renderProviderPresetNote = (
    channel: 'llm' | 'stt' | 'tts' | 'realtime',
    provider: string,
  ) => {
    const preset = providerPresetByValue(channel, provider)
    if (!preset) return null
    if (channel === 'realtime' && preset.status === 'inventory' && config?.realtime_effective_api_key_configured) {
      return (
        <p className="settings-voice-note settings-voice-note-warning">
          {tr('密钥已配置，Realtime runtime 待接入。', 'Key configured; Realtime runtime adapter pending.')}
          {preset.note ? ` ${preset.note}` : ''}
        </p>
      )
    }
    if (preset.status === 'runtime') {
      return (
        <p className="settings-voice-note">
          {tr('URL、模型和接口已预置；API Key 需要手动填写。', 'URL, model, and API shape are preset; enter the API key manually.')}
        </p>
      )
    }
    if (preset.status === 'pipecat') {
      return (
        <p className="settings-voice-note settings-voice-note-warning">
          {preset.note || tr('该 provider 已在 Pipecat 运行层出现，但当前设置模块还没有完整 adapter。', 'This provider is present in the Pipecat runtime layer, but this settings module does not have a full adapter yet.')}
        </p>
      )
    }
    return (
      <p className="settings-voice-note settings-voice-note-warning">
        {preset.note || tr('该 provider 已预置并可保存配置，但当前运行态还没有 adapter。', 'This provider is preset and can be saved, but the active runtime adapter is not wired yet.')}
      </p>
    )
  }

  const renderTtsRuntimeNote = () => {
    if (!config) return null
    const message = config.tts_runtime_message?.trim()
    if (config.tts_runtime_available) {
      return (
        <p className="settings-voice-note">
          {tr('TTS runtime is initialized; turn-based voice can play AI replies.', 'TTS runtime is initialized; turn-based voice can play AI replies.')}
        </p>
      )
    }
    return (
      <p className="settings-voice-note settings-voice-note-warning">
        {message || tr('TTS settings are not active in the current backend runtime. Save settings or restart the backend, then try again.', 'TTS settings are not active in the current backend runtime. Save settings or restart the backend, then try again.')}
      </p>
    )
  }

  const renderModuleConfig = () => {
    if (!activeModuleMeta) return null
    if (activeModule === 'llm') {
      return (
        <>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            {renderProviderSelect(form.llmProvider, llmProviderOptions, applyLlmProvider)}
          </Field>
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
          {renderCatalogSummary(llmChannel, 'Pipecat LLM')}
          {renderProviderPresetNote('llm', form.llmProvider)}
        </>
      )
    }
    if (activeModule === 'tts') {
      return (
        <>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            {renderProviderSelect(form.ttsProvider, ttsProviderOptions, applyTtsProvider)}
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
          {renderCatalogSummary(ttsChannel, 'Pipecat TTS')}
          {renderProviderPresetNote('tts', form.ttsProvider)}
          {renderTtsRuntimeNote()}
        </>
      )
    }
    if (activeModule === 'stt') {
      return (
        <>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            {renderProviderSelect(form.sttProvider, sttProviderOptions, applySttProvider)}
          </Field>
          <Field className="settings-voice-field" label={tr('基础 URL', 'Base URL')}>
            <Input value={form.sttBaseUrl} onChange={(e) => updateForm({ sttBaseUrl: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('模型', 'Model')}>
            <Input value={form.sttModel} onChange={(e) => updateForm({ sttModel: e.target.value })} />
          </Field>
          <label className="settings-checkbox-item settings-voice-check">
            <Checkbox
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
          {renderCatalogSummary(sttChannel, 'Pipecat STT')}
          {renderProviderPresetNote('stt', form.sttProvider)}
        </>
      )
    }
    if (activeModule === 'realtime') {
      return (
        <>
          <Field className="settings-voice-field" label={tr('服务商', 'Provider')}>
            {renderProviderSelect(form.realtimeProvider, realtimeProviderOptions, applyRealtimeProvider)}
          </Field>
          <Field className="settings-voice-field" label={tr('基础 URL', 'Base URL')}>
            <Input value={form.realtimeBaseUrl} onChange={(e) => updateForm({ realtimeBaseUrl: e.target.value })} />
          </Field>
          <Field className="settings-voice-field" label={tr('Realtime API 密钥', 'Realtime API Key')}>
            <Input
              type="password"
              value={form.realtimeApiKey}
              onChange={(e) => updateForm({ realtimeApiKey: e.target.value })}
              placeholder={config?.realtime_effective_api_key_configured ? keyText(true, config.realtime_api_key_preview) : tr('需要时手动填写 key', 'Enter the key manually when needed')}
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
            {tr('Realtime 不是单纯 TTS；它需要后端 /realtime runtime 接入连续音频、VAD、turn 和音频输出。', 'Realtime is not plain TTS; it requires a backend /realtime runtime for continuous audio, VAD, turn handling, and output audio.')}
          </p>
          {renderCatalogSummary(realtimeChannel, 'Pipecat realtime')}
          {renderProviderPresetNote('realtime', form.realtimeProvider)}
        </>
      )
    }
    return (
      <>
        <div className="settings-voice-readonly-grid">
          {renderCatalogSummary(transportChannel, 'Transport')}
          {renderCatalogSummary(vadChannel, 'VAD')}
          {renderCatalogSummary(turnChannel, 'Turn detection')}
        </div>
        <p className="settings-voice-note">
          {tr('当前真实运行链路固定为 FastAPI WebSocket transport、Silero VAD 和 Pipecat user turn processor/strategies。其它 Pipecat transport/VAD/turn provider 已进入 inventory，但还没有 runtime adapter。', 'The active runtime is fixed to FastAPI WebSocket transport, Silero VAD, and Pipecat user turn processors/strategies. Other Pipecat transport/VAD/turn providers are inventory only until adapters are wired.')}
        </p>
      </>
    )
  }

  return (
    <>
      <div className="settings-section-header actions-only">
        <div className="settings-header-actions">
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
          <Button
            className="settings-header-button settings-reset-button"
            variant="secondary"
            size="sm"
            onClick={loadConfig}
            disabled={loading || saving}
          >
            <RotateCcw size={14} />
            {tr('重置', 'Reset')}
          </Button>
        </div>
      </div>

      {notice && (
        <div className={notice.tone === 'error' ? 'settings-error' : 'settings-success'}>
          {notice.text}
        </div>
      )}

      {catalogError && (
        <div className="settings-warning">
          <AlertTriangle size={14} />
          <span>{tr('Pipecat provider catalog 加载失败：{message}', 'Pipecat provider catalog failed to load: {message}', { message: catalogError })}</span>
        </div>
      )}
      <div className="settings-voice-list" aria-label={tr('语音链路模块', 'Voice pipeline modules')}>
        {voiceModules.map((module) => (
          <button
            type="button"
            key={module.key}
            className={`settings-voice-module ${module.tone}`}
            onClick={() => setActiveModule(module.key)}
          >
            <span className="settings-voice-module-icon">{module.icon}</span>
            <span className="settings-voice-module-main">
              <span className="settings-voice-module-title-row">
                <strong>{module.title}</strong>
                <span className={`settings-voice-badge ${module.tone}`}>
                  {module.tone === 'ready'
                    ? <CheckCircle2 size={13} />
                    : module.tone === 'neutral'
                      ? <Clock3 size={13} />
                      : <AlertTriangle size={13} />}
                  {toneLabel(module.tone)}
                </span>
              </span>
              <span className="settings-voice-module-subtitle">{module.subtitle}</span>
            </span>
            <span className="settings-voice-module-meta">
              <strong>{module.model}</strong>
            </span>
            <ChevronRight size={18} className="settings-voice-module-chevron" />
          </button>
        ))}
      </div>

      <Dialog open={Boolean(activeModule)} onOpenChange={(open) => { if (!open) setActiveModule(null) }}>
        <DialogContent className="settings-voice-dialog">
          {activeModuleMeta && (
            <>
              <Button
                className="settings-voice-dialog-close"
                variant="ghost"
                size="icon"
                onClick={() => setActiveModule(null)}
                title={tr('关闭', 'Close')}
                aria-label={tr('关闭', 'Close')}
              >
                <X size={16} />
              </Button>
              <div className="settings-voice-dialog-title">
                <span className="settings-voice-module-icon">{activeModuleMeta.icon}</span>
                <div>
                  <DialogTitle className="settings-voice-dialog-heading">
                    {activeModuleMeta.title}
                  </DialogTitle>
                  <DialogDescription>{activeModuleMeta.subtitle}</DialogDescription>
                </div>
              </div>
              <div className="settings-voice-dialog-body">
                {renderModuleConfig()}
              </div>
              <div className="dialog-actions settings-voice-dialog-actions">
                <Button variant="primary" onClick={() => { setActiveModule(null); handleSave() }} disabled={loading || saving}>
                  <Save size={14} />
                  {saving ? t('common.saving') : tr('保存并应用', 'Save and Apply')}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <div className="settings-form-actions settings-voice-actions">
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
  const { isAdmin } = useAuthContext()
  const canUseManagementTabs = isAdmin
  const requestedTab = searchParams.get('tab')
  const availableTabs = canUseManagementTabs ? SETTINGS_TAB_KEYS : PERSONAL_SETTINGS_TAB_KEYS
  const activeTab = availableTabs.includes(requestedTab as TabKey)
    ? requestedTab as TabKey
    : 'personas'

  return (
    <SettingsShell activeTab={activeTab} canUseManagementTabs={canUseManagementTabs}>
      {activeTab === 'personas' && <PersonasTab />}
      {activeTab === 'scenarios' && <ScenariosTab />}
      {activeTab === 'members' && <TeamMembersTab />}
      {canUseManagementTabs && activeTab === 'organizations' && <OrganizationsTab />}
      {canUseManagementTabs && activeTab === 'config' && <ConfigTab />}
    </SettingsShell>
  )
}

export default SettingsPage
