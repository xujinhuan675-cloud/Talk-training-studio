import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  Medal,
  Target,
  Trophy,
  Users,
} from 'lucide-react'
import { useAuthContext } from '../contexts/AuthContext'
import {
  buildScenarioLeaderboardSummary,
  getScenarioTrainingProgress,
  scenarioTrainingCatalog,
  type ScenarioLeaderboardProgressUser,
  type ScenarioLeaderboardScenarioStat,
} from '../data/trainingScenarios'
import { getUserDisplayRoleName, type AuthUser } from '../services/auth'
import { APP_ROUTES } from '../appRoutes'
import './ScenarioLeaderboardPage.css'

const PROGRESS_STORAGE_PREFIX = 'talkwise.scenarioTraining.progress.v1'

const difficultyLabels: Record<ScenarioLeaderboardScenarioStat['difficulty'], string> = {
  easy: '轻量',
  medium: '标准',
  hard: '高压',
  expert: '专家',
}

const statusLabels: Partial<Record<ScenarioLeaderboardScenarioStat['status'], string>> = {
  not_started: '未开始',
  in_progress: '练习中',
  completed: '已完成',
}

function formatScore(score: number | null | undefined): string {
  return typeof score === 'number' ? String(score) : '--'
}

function formatGap(gap: number | null): string {
  if (gap === null) return '--'
  return gap > 0 ? `+${gap}` : String(gap)
}

function formatDate(value?: string): string {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function completionWidth(value: number): string {
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`
}

function visibleUsersForViewer(users: AuthUser[], currentUser: AuthUser | null): AuthUser[] {
  if (!currentUser) return []
  if (currentUser.systemRole === 'admin') return users
  return users.filter((user) => user.teamId === currentUser.teamId)
}

function buildProgressUsers(users: AuthUser[], currentUser: AuthUser | null): ScenarioLeaderboardProgressUser[] {
  return users.map((user) => ({
    userId: user.userId,
    name: user.name,
    teamId: user.teamId,
    teamName: user.teamName,
    roleName: getUserDisplayRoleName(user),
    progress: getScenarioTrainingProgress({ userId: user.userId, teamId: user.teamId }),
    useCatalogFallback: user.userId === currentUser?.userId,
  }))
}

export default function ScenarioLeaderboardPage() {
  const { currentUser, users } = useAuthContext()
  const [progressVersion, setProgressVersion] = useState(0)
  const [selectedUserId, setSelectedUserId] = useState(currentUser?.userId ?? '')

  useEffect(() => {
    if (currentUser?.userId) setSelectedUserId(currentUser.userId)
  }, [currentUser?.userId])

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (!event.key || event.key.startsWith(PROGRESS_STORAGE_PREFIX)) {
        setProgressVersion((version) => version + 1)
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  const visibleAuthUsers = useMemo(
    () => visibleUsersForViewer(users, currentUser),
    [currentUser, users],
  )
  const isManagementView = currentUser?.systemRole === 'admin' || currentUser?.systemRole === 'leader'
  const selectedUser = isManagementView
    ? visibleAuthUsers.find((user) => user.userId === selectedUserId)
      ?? currentUser
      ?? visibleAuthUsers[0]
      ?? null
    : currentUser
  const progressUsers = useMemo(() => {
    void progressVersion
    return buildProgressUsers(visibleAuthUsers, currentUser)
  }, [currentUser, progressVersion, visibleAuthUsers])
  const summary = useMemo(
    () => buildScenarioLeaderboardSummary(scenarioTrainingCatalog, progressUsers, selectedUser?.userId),
    [progressUsers, selectedUser?.userId],
  )
  const personal = summary.personal
  const team = summary.team
  const personalMissingRequired = personal
    ? Math.max(0, personal.totalRequired - personal.completedRequired)
    : 0
  const teamLabel = currentUser?.systemRole === 'admin'
    ? '全部团队'
    : currentUser?.teamName ?? selectedUser?.teamName ?? '当前团队'

  return (
    <main className="scenario-leaderboard-page">
      <section className="scenario-leaderboard-head">
        <div>
          <span className="scenario-leaderboard-kicker">
            <Trophy size={16} />
            {isManagementView ? '团队训练看板' : '我的排行状态'}
          </span>
          <h1>{isManagementView ? '团队能力概览' : '我的能力概览'}</h1>
        </div>
        <div className="scenario-leaderboard-actions">
          {isManagementView && visibleAuthUsers.length > 1 && (
            <label className="scenario-leaderboard-select">
              <span>查看成员</span>
              <select value={selectedUser?.userId ?? ''} onChange={(event) => setSelectedUserId(event.target.value)}>
                {visibleAuthUsers.map((user) => (
                  <option key={user.userId} value={user.userId}>
                    {user.name} · {user.teamName}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Link to={APP_ROUTES.practiceScenarios} className="scenario-leaderboard-link">
            <ClipboardList size={16} />
            场景训练
            <ArrowRight size={15} />
          </Link>
        </div>
      </section>

      <section className="scenario-leaderboard-scope" aria-label="榜单范围">
        <span>
          <Users size={15} />
          {teamLabel}
        </span>
      </section>

      {isManagementView ? (
        <>
          <section className="scenario-leaderboard-metrics" aria-label="团队榜概览">
            <div>
              <small>参与成员</small>
              <strong>{team.participants}</strong>
              <span>已有训练进度</span>
            </div>
            <div>
              <small>达标入榜</small>
              <strong>{team.ranked}</strong>
              <span>必练完成度 100%</span>
            </div>
            <div>
              <small>未完成</small>
              <strong className="warn">{team.unfinishedAll}</strong>
              <span>{team.unfinishedActive} 人已开始但未达标</span>
            </div>
            <div>
              <small>团队均分</small>
              <strong>{formatScore(team.teamAverage)}</strong>
              <span>入榜成员必练均分</span>
            </div>
          </section>

          <section className="scenario-leaderboard-grid">
            <div className="scenario-leaderboard-panel">
              <div className="scenario-leaderboard-panel-head">
                <h2>
                  <Medal size={17} />
                  团队榜
                </h2>
                <span>达标后入榜</span>
              </div>
              {team.ranks.length ? (
                <div className="scenario-leaderboard-table">
                  {team.ranks.map((row) => (
                    <article className={`scenario-leaderboard-row${row.isCurrentUser ? ' selected' : ''}`} key={row.userId}>
                      <span className="rank">#{row.rank}</span>
                      <div className="person">
                        <strong>{row.name}</strong>
                        <small>{row.teamName} · {row.roleName || '成员'} · 已练 {row.practicedCount}</small>
                      </div>
                      <span className="score">{formatScore(row.averageScore)}</span>
                      <span className="completion">{row.completedRequired}/{row.totalRequired}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="scenario-leaderboard-empty">
                  <AlertCircle size={16} />
                  暂无入榜成员
                </p>
              )}
            </div>

            <aside className="scenario-leaderboard-side">
              <section>
                <h2>
                  <BarChart3 size={16} />
                  团队薄弱维度
                </h2>
                {team.weakDimensions.length ? (
                  <div className="ability-list">
                    {team.weakDimensions.slice(0, 4).map((dimension) => (
                      <div key={dimension.dimensionId}>
                        <span>{dimension.name}</span>
                        <strong className={dimension.isWeak ? 'warn' : ''}>{dimension.averageScore}</strong>
                        <em>{dimension.sampleCount} 条评分 · {dimension.scenarioTitles.slice(0, 2).join('、')}</em>
                        <b style={{ width: completionWidth(dimension.averageScore) }} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">暂无评分数据</p>
                )}
              </section>

              <section>
                <h2>
                  <Target size={16} />
                  低分场景
                </h2>
                {team.scenarioAverages.length ? (
                  <div className="scenario-average-list">
                    {team.scenarioAverages.slice(0, 4).map((scenario) => (
                      <div key={scenario.scenarioId}>
                        <span>{scenario.title}</span>
                        <strong>{scenario.averageScore}</strong>
                        <small>{scenario.participantCount} 人 · {difficultyLabels[scenario.difficulty]}</small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">暂无场景均分</p>
                )}
              </section>
            </aside>
          </section>

          <section className="scenario-leaderboard-panel">
            <div className="scenario-leaderboard-panel-head">
              <h2>
                <ListIcon />
                团队未完成必练名单
              </h2>
              <span>{team.unfinishedAll} 人未达标</span>
            </div>
            {team.unfinished.length ? (
              <div className="unfinished-table">
                {team.unfinished.map((row) => (
                  <article className={`unfinished-row${row.isCurrentUser ? ' selected' : ''}`} key={row.userId}>
                    <div className="person">
                      <strong>{row.name}</strong>
                      <small>{row.teamName} · {row.status === 'in_progress' ? '进行中' : '未开始'}</small>
                    </div>
                    <div className="unfinished-progress">
                      <span>{row.completedRequired}/{row.totalRequired}</span>
                      <div>
                        <b style={{ width: completionWidth(row.completionRate) }} />
                      </div>
                    </div>
                    <div className="unfinished-missing">
                      {row.unfinishedRequired.length
                        ? row.unfinishedRequired.map((scenario) => scenario.title).join('、')
                        : '必练已完成，等待刷新入榜'}
                    </div>
                    <span className="score">{formatScore(row.averageScore)}</span>
                  </article>
                ))}
              </div>
            ) : (
              <p className="scenario-leaderboard-empty">
                <CheckCircle2 size={16} />
                全部成员已达标
              </p>
            )}
          </section>
        </>
      ) : (
        <section className="scenario-leaderboard-metrics scenario-leaderboard-metrics--personal" aria-label="我的排行概览">
          <div>
            <small>我的名次</small>
            <strong>{personal?.rank ? `#${personal.rank}` : '--'}</strong>
            <span>{personal?.status === 'ranked' ? `团队入榜成员 ${team.ranked} 人` : `还差 ${personalMissingRequired} 个必练场景入榜`}</span>
          </div>
          <div>
            <small>必练完成</small>
            <strong>{personal ? `${personal.completedRequired}/${personal.totalRequired}` : '--'}</strong>
            <span>{personal ? `${Math.round(personal.completionRate)}% 完成度` : '暂无进度'}</span>
          </div>
          <div>
            <small>必练均分</small>
            <strong>{formatScore(personal?.averageScore)}</strong>
            <span>完成全部必练后计入排行</span>
          </div>
          <div>
            <small>团队均分</small>
            <strong>{formatScore(team.teamAverage)}</strong>
            <span>入榜成员必练均分</span>
          </div>
        </section>
      )}

      <section className="scenario-leaderboard-personal">
        <div className="scenario-leaderboard-panel-head">
          <h2>
            <Users size={17} />
            {isManagementView ? '成员能力概览' : '我的能力概览'}
          </h2>
          <span>{personal?.user.name ?? '暂无成员'}</span>
        </div>

        {personal ? (
          <>
            <div className="personal-summary">
              <div className="personal-identity">
                <span>{personal.user.name.slice(0, 1)}</span>
                <div>
                  <strong>{personal.user.name}</strong>
                  <small>{personal.user.teamName} · {personal.user.roleName || '成员'}</small>
                </div>
              </div>
              <div>
                <small>排名</small>
                <strong>{personal.rank ? `#${personal.rank}` : '--'}</strong>
              </div>
              <div>
                <small>必练均分</small>
                <strong>{formatScore(personal.averageScore)}</strong>
              </div>
              <div>
                <small>总均分</small>
                <strong>{formatScore(personal.overallAverage)}</strong>
              </div>
              <div>
                <small>最近练习</small>
                <strong>{formatDate(personal.latestPracticedAt)}</strong>
              </div>
            </div>

            {personal.status !== 'ranked' && (
              <div className="scenario-leaderboard-banner">
                <AlertCircle size={16} />
                {personalMissingRequired > 0
                  ? `还有 ${personalMissingRequired} 个必练场景未完成：${personal.unfinishedRequired.map((scenario) => scenario.title).join('、')}`
                  : '等待评分刷新后入榜。'}
              </div>
            )}

            <div className="personal-grid">
              <section>
                <h3>能力画像</h3>
                {personal.abilityProfile.length ? (
                  <div className="ability-list">
                    {personal.abilityProfile.map((dimension) => (
                      <div key={dimension.dimensionId}>
                        <span>{dimension.name}</span>
                        <strong className={dimension.isWeak ? 'warn' : ''}>{dimension.averageScore}</strong>
                        <em>{dimension.sampleCount} 条评分</em>
                        <b style={{ width: completionWidth(dimension.averageScore) }} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">暂无评分数据，完成一次有分训练后生成画像。</p>
                )}
              </section>

              <section>
                <h3>场景训练数据</h3>
                <div className="personal-scenario-list">
                  {personal.scenarioStats.map((scenario) => (
                    <article key={scenario.scenarioId}>
                      <div>
                        <strong>{scenario.title}</strong>
                        <small>
                          {scenario.required ? '必练' : '选练'} · {difficultyLabels[scenario.difficulty]} · {statusLabels[scenario.status]}
                        </small>
                      </div>
                      <span>{formatScore(scenario.score)}</span>
                      <small>团队 {formatScore(scenario.teamAverage)} · 差值 {formatGap(scenario.gap)}</small>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          </>
        ) : (
          <p className="scenario-leaderboard-empty">暂无成员</p>
        )}
      </section>
    </main>
  )
}

function ListIcon() {
  return <ClipboardList size={17} />
}
