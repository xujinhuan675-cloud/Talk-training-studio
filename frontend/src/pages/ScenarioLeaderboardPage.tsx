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
import { useI18n, type Locale, type TranslateInline } from '../i18n'
import { APP_ROUTES } from '../appRoutes'
import './ScenarioLeaderboardPage.css'

const PROGRESS_STORAGE_PREFIX = 'talkwise.scenarioTraining.progress.v1'

function formatScore(score: number | null | undefined): string {
  return typeof score === 'number' ? String(score) : '--'
}

function formatGap(gap: number | null): string {
  if (gap === null) return '--'
  return gap > 0 ? `+${gap}` : String(gap)
}

function formatDate(value: string | undefined, tr: TranslateInline, locale: Locale): string {
  if (!value) return tr('暂无', 'None')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', { month: '2-digit', day: '2-digit' })
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

function getDifficultyLabel(
  difficulty: ScenarioLeaderboardScenarioStat['difficulty'],
  tr: TranslateInline,
): string {
  if (difficulty === 'easy') return tr('轻量', 'Light')
  if (difficulty === 'medium') return tr('标准', 'Standard')
  if (difficulty === 'hard') return tr('高压', 'Pressure')
  return tr('专家', 'Expert')
}

function getStatusLabel(
  status: ScenarioLeaderboardScenarioStat['status'],
  tr: TranslateInline,
): string {
  if (status === 'not_started') return tr('未开始', 'Not started')
  if (status === 'in_progress') return tr('练习中', 'In progress')
  if (status === 'completed') return tr('已完成', 'Completed')
  return tr('无记录', 'No record')
}

export default function ScenarioLeaderboardPage() {
  const { tr, locale } = useI18n()
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
    ? tr('全部团队', 'All teams')
    : currentUser?.teamName ?? selectedUser?.teamName ?? tr('当前团队', 'Current team')

  return (
    <main className="scenario-leaderboard-page">
      <section className="scenario-leaderboard-head">
        <div>
          <span className="scenario-leaderboard-kicker">
            <Trophy size={16} />
            {isManagementView ? tr('训练看板', 'Training board') : tr('我的训练', 'My training')}
          </span>
          <h1>{isManagementView ? tr('团队进度', 'Team progress') : tr('我的进度', 'My progress')}</h1>
        </div>
        <div className="scenario-leaderboard-actions">
          {isManagementView && visibleAuthUsers.length > 1 && (
            <label className="scenario-leaderboard-select">
              <span>{tr('成员', 'Member')}</span>
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
            {tr('场景训练', 'Scenario training')}
            <ArrowRight size={15} />
          </Link>
        </div>
      </section>

      <section className="scenario-leaderboard-scope" aria-label={tr('训练范围', 'Training scope')}>
        <span>
          <Users size={15} />
          {teamLabel}
        </span>
      </section>

      {isManagementView ? (
        <>
          <section className="scenario-leaderboard-metrics" aria-label={tr('团队训练指标', 'Team training metrics')}>
            <div>
              <small>{tr('参与成员', 'Participants')}</small>
              <strong>{team.participants}</strong>
              <span>{tr('有训练记录', 'With progress')}</span>
            </div>
            <div>
              <small>{tr('已达标', 'Qualified')}</small>
              <strong>{team.ranked}</strong>
              <span>{tr('完成必练', 'Required complete')}</span>
            </div>
            <div>
              <small>{tr('未达标', 'Not qualified')}</small>
              <strong className="warn">{team.unfinishedAll}</strong>
              <span>{tr('{count} 人进行中', '{count} in progress', { count: team.unfinishedActive })}</span>
            </div>
            <div>
              <small>{tr('团队均分', 'Team average')}</small>
              <strong>{formatScore(team.teamAverage)}</strong>
              <span>{tr('必练得分', 'Required score')}</span>
            </div>
          </section>

          <section className="scenario-leaderboard-grid">
            <div className="scenario-leaderboard-panel">
              <div className="scenario-leaderboard-panel-head">
                <h2>
                  <Medal size={17} />
                  {tr('排行', 'Ranking')}
                </h2>
                <span>{tr('达标后入榜', 'Qualified users only')}</span>
              </div>
              {team.ranks.length ? (
                <div className="scenario-leaderboard-table">
                  {team.ranks.map((row) => (
                    <article className={`scenario-leaderboard-row${row.isCurrentUser ? ' selected' : ''}`} key={row.userId}>
                      <span className="rank">#{row.rank}</span>
                      <div className="person">
                        <strong>{row.name}</strong>
                        <small>
                          {row.teamName} · {row.roleName || tr('成员', 'Member')} · {tr('已练 {count}', '{count} practiced', { count: row.practicedCount })}
                        </small>
                      </div>
                      <span className="score">{formatScore(row.averageScore)}</span>
                      <span className="completion">{row.completedRequired}/{row.totalRequired}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="scenario-leaderboard-empty">
                  <AlertCircle size={16} />
                  {tr('暂无入榜成员', 'No qualified members')}
                </p>
              )}
            </div>

            <aside className="scenario-leaderboard-side">
              <section>
                <h2>
                  <BarChart3 size={16} />
                  {tr('薄弱维度', 'Weak dimensions')}
                </h2>
                {team.weakDimensions.length ? (
                  <div className="ability-list">
                    {team.weakDimensions.slice(0, 4).map((dimension) => (
                      <div key={dimension.dimensionId}>
                        <span>{dimension.name}</span>
                        <strong className={dimension.isWeak ? 'warn' : ''}>{dimension.averageScore}</strong>
                        <em>
                          {tr('{count} 条评分', '{count} scores', { count: dimension.sampleCount })}
                          {' · '}
                          {dimension.scenarioTitles.slice(0, 2).join(tr('、', ', '))}
                        </em>
                        <b style={{ width: completionWidth(dimension.averageScore) }} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">{tr('暂无评分数据', 'No score data')}</p>
                )}
              </section>

              <section>
                <h2>
                  <Target size={16} />
                  {tr('低分场景', 'Low-score scenarios')}
                </h2>
                {team.scenarioAverages.length ? (
                  <div className="scenario-average-list">
                    {team.scenarioAverages.slice(0, 4).map((scenario) => (
                      <div key={scenario.scenarioId}>
                        <span>{scenario.title}</span>
                        <strong>{scenario.averageScore}</strong>
                        <small>
                          {tr('{count} 人', '{count} users', { count: scenario.participantCount })}
                          {' · '}
                          {getDifficultyLabel(scenario.difficulty, tr)}
                        </small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">{tr('暂无场景均分', 'No scenario averages')}</p>
                )}
              </section>
            </aside>
          </section>

          <section className="scenario-leaderboard-panel">
            <div className="scenario-leaderboard-panel-head">
              <h2>
                <ListIcon />
                {tr('未达标名单', 'Not qualified')}
              </h2>
              <span>{tr('{count} 人', '{count} users', { count: team.unfinishedAll })}</span>
            </div>
            {team.unfinished.length ? (
              <div className="unfinished-table">
                {team.unfinished.map((row) => (
                  <article className={`unfinished-row${row.isCurrentUser ? ' selected' : ''}`} key={row.userId}>
                    <div className="person">
                      <strong>{row.name}</strong>
                      <small>{row.teamName} · {getStatusLabel(row.status, tr)}</small>
                    </div>
                    <div className="unfinished-progress">
                      <span>{row.completedRequired}/{row.totalRequired}</span>
                      <div>
                        <b style={{ width: completionWidth(row.completionRate) }} />
                      </div>
                    </div>
                    <div className="unfinished-missing">
                      {row.unfinishedRequired.length
                        ? row.unfinishedRequired.map((scenario) => scenario.title).join(tr('、', ', '))
                        : tr('必练已完成，等待入榜', 'Required complete; waiting for ranking')}
                    </div>
                    <span className="score">{formatScore(row.averageScore)}</span>
                  </article>
                ))}
              </div>
            ) : (
              <p className="scenario-leaderboard-empty">
                <CheckCircle2 size={16} />
                {tr('全部成员已达标', 'All members qualified')}
              </p>
            )}
          </section>
        </>
      ) : (
        <section className="scenario-leaderboard-metrics scenario-leaderboard-metrics--personal" aria-label={tr('我的训练指标', 'My training metrics')}>
          <div>
            <small>{tr('我的名次', 'My rank')}</small>
            <strong>{personal?.rank ? `#${personal.rank}` : '--'}</strong>
            <span>
              {personal?.status === 'ranked'
                ? tr('团队入榜 {count} 人', '{count} qualified teammates', { count: team.ranked })
                : tr('还差 {count} 个必练', '{count} required left', { count: personalMissingRequired })}
            </span>
          </div>
          <div>
            <small>{tr('必练完成', 'Required complete')}</small>
            <strong>{personal ? `${personal.completedRequired}/${personal.totalRequired}` : '--'}</strong>
            <span>
              {personal
                ? tr('{count}% 完成', '{count}% complete', { count: Math.round(personal.completionRate) })
                : tr('暂无进度', 'No progress')}
            </span>
          </div>
          <div>
            <small>{tr('必练均分', 'Required average')}</small>
            <strong>{formatScore(personal?.averageScore)}</strong>
            <span>{tr('完成后入榜', 'Ranks after completion')}</span>
          </div>
          <div>
            <small>{tr('团队均分', 'Team average')}</small>
            <strong>{formatScore(team.teamAverage)}</strong>
            <span>{tr('必练得分', 'Required score')}</span>
          </div>
        </section>
      )}

      <section className="scenario-leaderboard-personal">
        <div className="scenario-leaderboard-panel-head">
          <h2>
            <Users size={17} />
            {isManagementView ? tr('成员能力', 'Member ability') : tr('能力画像', 'Ability profile')}
          </h2>
          <span>{personal?.user.name ?? tr('暂无成员', 'No member')}</span>
        </div>

        {personal ? (
          <>
            <div className="personal-summary">
              <div className="personal-identity">
                <span>{personal.user.name.slice(0, 1)}</span>
                <div>
                  <strong>{personal.user.name}</strong>
                  <small>{personal.user.teamName} · {personal.user.roleName || tr('成员', 'Member')}</small>
                </div>
              </div>
              <div>
                <small>{tr('排名', 'Rank')}</small>
                <strong>{personal.rank ? `#${personal.rank}` : '--'}</strong>
              </div>
              <div>
                <small>{tr('必练均分', 'Required average')}</small>
                <strong>{formatScore(personal.averageScore)}</strong>
              </div>
              <div>
                <small>{tr('总均分', 'Overall average')}</small>
                <strong>{formatScore(personal.overallAverage)}</strong>
              </div>
              <div>
                <small>{tr('最近练习', 'Latest practice')}</small>
                <strong>{formatDate(personal.latestPracticedAt, tr, locale)}</strong>
              </div>
            </div>

            {personal.status !== 'ranked' && (
              <div className="scenario-leaderboard-banner">
                <AlertCircle size={16} />
                {personalMissingRequired > 0
                  ? tr('还有 {count} 个必练未完成：{items}', '{count} required scenarios left: {items}', {
                    count: personalMissingRequired,
                    items: personal.unfinishedRequired.map((scenario) => scenario.title).join(tr('、', ', ')),
                  })
                  : tr('等待评分刷新后入榜。', 'Waiting for score refresh to rank.')}
              </div>
            )}

            <div className="personal-grid">
              <section>
                <h3>{tr('能力画像', 'Ability profile')}</h3>
                {personal.abilityProfile.length ? (
                  <div className="ability-list">
                    {personal.abilityProfile.map((dimension) => (
                      <div key={dimension.dimensionId}>
                        <span>{dimension.name}</span>
                        <strong className={dimension.isWeak ? 'warn' : ''}>{dimension.averageScore}</strong>
                        <em>{tr('{count} 条评分', '{count} scores', { count: dimension.sampleCount })}</em>
                        <b style={{ width: completionWidth(dimension.averageScore) }} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="scenario-leaderboard-empty">{tr('暂无评分数据', 'No score data')}</p>
                )}
              </section>

              <section>
                <h3>{tr('场景数据', 'Scenario data')}</h3>
                <div className="personal-scenario-list">
                  {personal.scenarioStats.map((scenario) => (
                    <article key={scenario.scenarioId}>
                      <div>
                        <strong>{scenario.title}</strong>
                        <small>
                          {scenario.required ? tr('必练', 'Required') : tr('选练', 'Optional')}
                          {' · '}
                          {getDifficultyLabel(scenario.difficulty, tr)}
                          {' · '}
                          {getStatusLabel(scenario.status, tr)}
                        </small>
                      </div>
                      <span>{formatScore(scenario.score)}</span>
                      <small>
                        {tr('团队 {score}', 'Team {score}', { score: formatScore(scenario.teamAverage) })}
                        {' · '}
                        {tr('差值 {gap}', 'Gap {gap}', { gap: formatGap(scenario.gap) })}
                      </small>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          </>
        ) : (
          <p className="scenario-leaderboard-empty">{tr('暂无成员', 'No member')}</p>
        )}
      </section>
    </main>
  )
}

function ListIcon() {
  return <ClipboardList size={17} />
}
