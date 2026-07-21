import { useEffect, useState } from 'react'
import {
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
  updatePersona,
  type Organization,
  type Team,
  type PersonaRelationship,
  type PersonaSummary,
} from '../services/api'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from './ui/dialog'
import { Field, Input, Select, Textarea } from './ui/form'
import { SegmentedControl, type SegmentedControlOption } from './ui/segmented-control'
import './OrganizationDialog.css'

interface OrganizationDialogProps {
  open: boolean
  onClose: () => void
  onOrgChanged: () => void
  personas: PersonaSummary[]
}

type OrgDialogTab = 'info' | 'teams' | 'relationships'

const getErrorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : 'Operation failed'

const REL_LABELS: Record<string, string> = {
  superior: '上级',
  subordinate: '下级',
  peer: '同级',
  cross_department: '跨部门',
}

export default function OrganizationDialog({ open, onClose, onOrgChanged, personas }: OrganizationDialogProps) {
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [relationships, setRelationships] = useState<PersonaRelationship[]>([])
  const [tab, setTab] = useState<OrgDialogTab>('info')

  // Form state for org info
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

  const loadOrgDetail = async (orgId: number) => {
    const detail = await fetchOrganizationDetail(orgId)
    setSelectedOrg(detail.organization)
    setTeams(detail.teams)
    setOrgName(detail.organization.name)
    setOrgIndustry(detail.organization.industry)
    setOrgDescription(detail.organization.description)
    setOrgContextPrompt(detail.organization.context_prompt)
    fetchRelationships(orgId).then(setRelationships).catch(() => {})
  }

  useEffect(() => {
    if (open) {
      loadOrgs()
      setError(null)
      setTab('info')
    }
  }, [open])

  // Auto-load first org
  useEffect(() => {
    if (orgs.length > 0 && !selectedOrg) {
      loadOrgDetail(orgs[0].id)
    }
  }, [orgs])

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
      onOrgChanged()
    } catch (e) {
      setError(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteOrg = async () => {
    if (!selectedOrg || !confirm(`确定删除组织「${selectedOrg.name}」？`)) return
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
      onOrgChanged()
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  const handleAddTeam = async () => {
    if (!selectedOrg || !newTeamName.trim()) return
    try {
      await createTeam(selectedOrg.id, { name: newTeamName.trim() })
      setNewTeamName('')
      await loadOrgDetail(selectedOrg.id)
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  const handleDeleteTeam = async (teamId: number) => {
    if (!selectedOrg) return
    try {
      await deleteTeam(selectedOrg.id, teamId)
      await loadOrgDetail(selectedOrg.id)
    } catch (e) {
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
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  const handleDeleteRelationship = async (relId: number) => {
    if (!selectedOrg) return
    try {
      await deleteRelationship(selectedOrg.id, relId)
      fetchRelationships(selectedOrg.id).then(setRelationships)
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  // Personas available to add to a team: either in this org without a team, or not in any org
  const assignedTeamIds = new Set(teams.map((t) => t.id))
  const unassignedPersonas = selectedOrg
    ? personas.filter((p) =>
        !p.team_id || !assignedTeamIds.has(p.team_id)
      ).filter((p) => p.id !== 'TEMPLATE')
    : []

  const handleAssignToTeam = async (personaId: string, teamId: number) => {
    if (!selectedOrg) return
    try {
      await updatePersona(personaId, { organization_id: selectedOrg.id, team_id: teamId })
      onOrgChanged()
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  const handleRemoveFromTeam = async (personaId: string) => {
    if (!selectedOrg) return
    try {
      await updatePersona(personaId, { team_id: null })
      onOrgChanged()
    } catch (e) {
      setError(getErrorMessage(e))
    }
  }

  const personaName = (pid: string) => personas.find((p) => p.id === pid)?.name || pid

  const tabOptions: SegmentedControlOption<OrgDialogTab>[] = [
    { value: 'info', label: '基本信息' },
    { value: 'teams', label: '团队', disabled: !selectedOrg },
    { value: 'relationships', label: '角色关系', disabled: !selectedOrg },
  ]

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <DialogContent className="org-dialog" aria-describedby={undefined}>
        <DialogTitle asChild className="org-dialog-title">
          <h3>{selectedOrg ? '编辑组织' : '创建组织'}</h3>
        </DialogTitle>

        {orgs.length > 1 && (
          <div className="org-selector-panel">
            <Select
              aria-label="选择组织"
              className="org-selector"
              value={selectedOrg?.id ?? ''}
              onChange={(e) => e.target.value && loadOrgDetail(Number(e.target.value))}
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </Select>
          </div>
        )}

        <div className="org-tabs-row">
          <SegmentedControl
            ariaLabel="组织管理视图"
            className="org-tabs"
            options={tabOptions}
            size="sm"
            value={tab}
            onValueChange={setTab}
          />
        </div>

        <div className="dialog-body org-tab-content">
          {tab === 'info' && (
            <>
              <Field className="field-label" label="组织名称">
                <Input
                  type="text"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  placeholder="如：Acme Corp"
                />
              </Field>
              <Field className="field-label" label="行业">
                <Input
                  type="text"
                  value={orgIndustry}
                  onChange={(e) => setOrgIndustry(e.target.value)}
                  placeholder="如：SaaS / 金融 / 制造"
                />
              </Field>
              <Field className="field-label org-description-field" label="组织描述">
                <Textarea
                  value={orgDescription}
                  onChange={(e) => setOrgDescription(e.target.value)}
                  placeholder="组织的业务、产品、文化..."
                />
              </Field>
              <Field className="field-label org-context-field" label="上下文提示词">
                <Textarea
                  value={orgContextPrompt}
                  onChange={(e) => setOrgContextPrompt(e.target.value)}
                  placeholder="注入所有角色 system prompt 的组织背景..."
                />
              </Field>
            </>
          )}

          {tab === 'teams' && selectedOrg && (
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
                          <Button
                            className="team-delete-btn"
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteTeam(t.id)}
                          >
                            删除
                          </Button>
                        </div>
                        <div className="team-members">
                          {members.length > 0 ? (
                            members.map((p) => (
                              <span key={p.id} className="team-member-chip">
                                <span className="team-member-dot" style={{ background: p.avatar_color || '#999' }} />
                                {p.name}
                                <Button
                                  className="team-member-remove"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleRemoveFromTeam(p.id)}
                                  title="移出团队"
                                >
                                  &times;
                                </Button>
                              </span>
                            ))
                          ) : (
                            <span className="team-members-empty">暂无成员</span>
                          )}
                          {unassignedPersonas.length > 0 && (
                            <Select
                              className="team-add-member-select"
                              value=""
                              onChange={(e) => e.target.value && handleAssignToTeam(e.target.value, t.id)}
                            >
                              <option value="">+ 添加角色</option>
                              {unassignedPersonas.map((p) => (
                                <option key={p.id} value={p.id}>{p.name} ({p.role})</option>
                              ))}
                            </Select>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="empty-hint">暂无团队，添加第一个吧</div>
              )}

              {/* Unassigned personas */}
              {unassignedPersonas.length > 0 && teams.length > 0 && (
                <div className="unassigned-hint">
                  <span className="unassigned-hint-label">未分配：</span>
                  <span>{unassignedPersonas.map((p) => p.name).join('、')}</span>
                </div>
              )}

              <div className="add-team-form" style={{ marginTop: 12 }}>
                <Input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  placeholder="输入团队名称..."
                  onKeyDown={(e) => e.key === 'Enter' && handleAddTeam()}
                />
                <Button variant="primary" onClick={handleAddTeam} disabled={!newTeamName.trim()}>
                  添加团队
                </Button>
              </div>
            </>
          )}

          {tab === 'relationships' && selectedOrg && (
            <>
              {relationships.length > 0 ? (
                <div className="rel-list">
                  {relationships.map((r) => (
                    <div key={r.id} className="rel-item">
                      <div className="rel-item-content">
                        <span className="rel-item-persona">{personaName(r.from_persona_id)}</span>
                        <span className={`rel-type-badge ${r.relationship_type}`}>
                          {REL_LABELS[r.relationship_type] || r.relationship_type}
                        </span>
                        <span className="rel-item-persona">{personaName(r.to_persona_id)}</span>
                        {r.description && <span className="rel-item-desc">— {r.description}</span>}
                      </div>
                      <Button
                        className="team-delete-btn"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteRelationship(r.id)}
                      >
                        删除
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-hint">暂无角色关系</div>
              )}
              <div className="add-rel-form">
                <Select value={relFrom} onChange={(e) => setRelFrom(e.target.value)}>
                  <option value="">选择角色</option>
                  {personas.filter((p) => p.id !== relTo).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Select value={relType} onChange={(e) => setRelType(e.target.value)}>
                  <option value="superior">上级</option>
                  <option value="subordinate">下级</option>
                  <option value="peer">同级</option>
                  <option value="cross_department">跨部门</option>
                </Select>
                <Select value={relTo} onChange={(e) => setRelTo(e.target.value)}>
                  <option value="">选择角色</option>
                  {personas.filter((p) => p.id !== relFrom).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </Select>
                <Input
                  type="text"
                  value={relDesc}
                  onChange={(e) => setRelDesc(e.target.value)}
                  placeholder="描述（可选）"
                />
                <Button
                  variant="primary"
                  onClick={handleAddRelationship}
                  disabled={!relFrom || !relTo || relFrom === relTo}
                >
                  添加
                </Button>
              </div>
            </>
          )}

          {error && <div className="dialog-error">{error}</div>}
        </div>

        <div className="dialog-actions">
          {selectedOrg && (
            <Button variant="danger" onClick={handleDeleteOrg}>删除组织</Button>
          )}
          <Button variant="secondary" onClick={onClose}>关闭</Button>
          {tab === 'info' && (
            <Button variant="primary" onClick={handleSaveOrg} disabled={saving || !orgName.trim()}>
              {saving ? '保存中...' : '保存'}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
