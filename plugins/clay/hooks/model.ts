// Pure helpers for the progress band and pane. No imports from the host, so they can be tested with plain Node.

export type Stage = 'spec' | 'build' | 'waiting-input' | 'review' | 'approve' | 'merged' | 'committed' | 'needs-human'

// What the orchestrator asked for when it spawned an agent of the job.
export type AgentInfo = { model: string; effort: string; tokens: number; ms: number; runs: number }

export type PlanTask = { n: number; title: string; tier: string; after: number[] }

export type Job = {
  id: string
  plan: string
  task: number
  started: number | null
  updated: number | null
  repo: string
  tier: string
  stage: Stage
  round: number
  reviewers: string[]
  reviews: Record<string, string>
  agents: Record<string, AgentInfo>
  tokens: number
  agentMs: number
}

// A run lock: while it is fresh, the plan and its spec are protected from edits.
export type Lock = { plan: string; runId: string; since: number; heartbeat: number; protect: string[] }

const STALE_MS = 30 * 60_000

export type Run = { plan: string; path: string; total: number; done: number; tasks: PlanTask[] }

export type PlanView = {
  plan: string
  path: string
  total: number
  done: number
  running: Job[]
  waiting: Job[]
  finished: Job[]
  planned: PlanTask[]
  tasks: PlanTask[]
  tokens: number
  agentMs: number
  lock: Lock | null
}

export type Summary = { plans: PlanView[]; waiting: number; running: number }

const STAGES: readonly string[] = ['spec', 'build', 'waiting-input', 'review', 'approve', 'merged', 'committed', 'needs-human']
const LANDED: readonly string[] = ['merged', 'committed']
const NEEDS_USER: readonly string[] = ['needs-human', 'waiting-input']

const toMs = (v: unknown): number | null => {
  if (typeof v !== 'string') return null
  const t = Date.parse(v)
  return Number.isNaN(t) ? null : t
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

function parseAgents(raw: unknown): Record<string, AgentInfo> {
  const out: Record<string, AgentInfo> = {}
  if (!isRecord(raw)) return out
  for (const [role, info] of Object.entries(raw)) {
    if (isRecord(info) && typeof info.model === 'string') {
      const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
      out[role] = { model: info.model, effort: typeof info.effort === 'string' ? info.effort : '', tokens: num(info.tokens), ms: num(info.ms), runs: num(info.runs) }
    }
  }
  return out
}

export function parseJob(text: string): Job | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!isRecord(raw) || typeof raw.id !== 'string' || typeof raw.plan !== 'string' || typeof raw.stage !== 'string') return null
  if (!STAGES.includes(raw.stage)) return null
  const agents = parseAgents(raw.agents)
  const reviews = isRecord(raw.reviews) ? Object.fromEntries(Object.entries(raw.reviews).map(([k, v]) => [k, String(v)])) : {}
  return {
    id: raw.id,
    plan: raw.plan,
    task: typeof raw.task === 'number' ? raw.task : 0,
    started: toMs(raw.started),
    updated: toMs(raw.updated),
    repo: typeof raw.repo === 'string' ? raw.repo : '',
    tier: typeof raw.tier === 'string' ? raw.tier : 'medium',
    stage: raw.stage as Stage,
    round: typeof raw.round === 'number' ? raw.round : 0,
    reviewers: Array.isArray(raw.reviewers) ? raw.reviewers.map(String) : [],
    reviews,
    agents,
    tokens: Object.values(agents).reduce((n, a) => n + a.tokens, 0),
    agentMs: Object.values(agents).reduce((n, a) => n + a.ms, 0),
  }
}

export function parseRun(text: string): Run | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!isRecord(raw) || typeof raw.plan !== 'string') return null
  const tasks: PlanTask[] = []
  if (Array.isArray(raw.tasks)) {
    for (const t of raw.tasks) {
      if (isRecord(t) && typeof t.n === 'number' && typeof t.title === 'string') {
        tasks.push({
          n: t.n,
          title: t.title,
          tier: typeof t.tier === 'string' ? t.tier : 'medium',
          after: Array.isArray(t.after) ? t.after.filter((x): x is number => typeof x === 'number') : [],
        })
      }
    }
  }
  return {
    plan: raw.plan,
    path: typeof raw.path === 'string' ? raw.path : '',
    total: typeof raw.total === 'number' ? raw.total : 0,
    done: typeof raw.done === 'number' ? raw.done : 0,
    tasks,
  }
}

export function summarize(runs: Run[], jobs: Job[], locks: Lock[] = []): Summary {
  const plans = new Map<string, Job[]>()
  for (const job of jobs) plans.set(job.plan, [...(plans.get(job.plan) ?? []), job])
  for (const run of runs) if (!plans.has(run.plan)) plans.set(run.plan, [])
  for (const lock of locks) if (!plans.has(lock.plan)) plans.set(lock.plan, [])

  const views: PlanView[] = []
  for (const [plan, list] of plans) {
    const run = runs.find(r => r.plan === plan)
    const landed = list.filter(j => LANDED.includes(j.stage)).length
    const started = new Set(list.map(j => j.task))
    views.push({
      plan,
      path: run?.path ?? '',
      total: run && run.total > 0 ? run.total : run && run.tasks.length > 0 ? run.tasks.length : list.length,
      done: Math.max(run?.done ?? 0, landed),
      running: list.filter(j => !LANDED.includes(j.stage) && !NEEDS_USER.includes(j.stage)),
      waiting: list.filter(j => NEEDS_USER.includes(j.stage)),
      finished: list.filter(j => LANDED.includes(j.stage)),
      planned: (run?.tasks ?? []).filter(t => !started.has(t.n)),
      tasks: run?.tasks ?? [],
      tokens: list.reduce((n, j) => n + j.tokens, 0),
      agentMs: list.reduce((n, j) => n + j.agentMs, 0),
      lock: locks.find(l => l.plan === plan) ?? null,
    })
  }
  return {
    plans: views,
    waiting: views.reduce((n, v) => n + v.waiting.length, 0),
    running: views.reduce((n, v) => n + v.running.length, 0),
  }
}

export function bar(done: number, total: number, width = 10): string {
  if (total <= 0) return ''
  const filled = Math.min(width, Math.max(0, Math.round((width * done) / total)))
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

// Plans that have something running or waiting, the ones that need the user first.
export function activePlans(summary: Summary): PlanView[] {
  return summary.plans
    .filter(p => p.running.length + p.waiting.length > 0)
    .sort((a, b) => b.waiting.length - a.waiting.length)
}

export function barParts(done: number, total: number, width = 10): { filled: string; empty: string } {
  if (total <= 0) return { filled: '', empty: '' }
  const filled = Math.min(width, Math.max(0, Math.round((width * done) / total)))
  return { filled: '█'.repeat(filled), empty: '░'.repeat(width - filled) }
}

// The ids of the jobs that need the user, at most `max` of them, then how many more.
export function waitingLabel(summary: Summary, max = 3): string {
  const ids = summary.plans.flatMap(p => p.waiting.map(j => j.id)).sort()
  if (ids.length <= max) return ids.join(', ')
  return `${ids.slice(0, max).join(', ')} +${ids.length - max}`
}

export function phaseLabel(job: Job): string {
  if (NEEDS_USER.includes(job.stage)) return job.stage === 'waiting-input' ? 'waiting for you' : 'needs you'
  if (job.stage === 'review') {
    const passed = job.reviewers.filter(r => job.reviews[r] === 'PASS').length
    return `review r${job.round} ${passed}/${job.reviewers.length}`
  }
  return job.stage
}

export function waitingIds(jobs: Job[]): Set<string> {
  return new Set(jobs.filter(j => NEEDS_USER.includes(j.stage)).map(j => j.id))
}

export type Fs = {
  list(path?: string): Promise<{ name: string; kind: string }[]>
  read(path: string): Promise<string>
  exists(path: string): Promise<boolean>
}

const SKIP_DIRS = new Set(['node_modules', 'vendor', 'dist', 'build'])
const MAX_JOBS = 300

async function jobsFolders(fs: Fs): Promise<string[]> {
  const folders: string[] = []
  if (await fs.exists('factory/jobs')) folders.push('factory/jobs')
  let here: { name: string; kind: string }[] = []
  try {
    here = await fs.list('.')
  } catch {
    return folders
  }
  for (const entry of here) {
    if (entry.kind !== 'dir' || entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue
    if (await fs.exists(`${entry.name}/factory/jobs`)) folders.push(`${entry.name}/factory/jobs`)
  }
  return folders
}

// Reads the state the run command writes: job.json per job and _runs/<plan>.json per plan.
// Looks in the working folder and one level below it. A file that cannot be read or parsed is skipped.
export async function scan(fs: Fs): Promise<{ runs: Run[]; jobs: Job[]; locks: Lock[] }> {
  const runs: Run[] = []
  const jobs: Job[] = []
  const locks: Lock[] = []
  for (const base of await jobsFolders(fs)) {
    let entries: { name: string; kind: string }[] = []
    try {
      entries = await fs.list(base)
    } catch {
      continue
    }
    for (const entry of entries) {
      if (entry.kind !== 'dir') continue
      if (entry.name === '_runs') {
        let files: { name: string; kind: string }[] = []
        try {
          files = await fs.list(`${base}/_runs`)
        } catch {
          continue
        }
        for (const f of files.filter(x => x.name.endsWith('.json'))) {
          const run = await fs.read(`${base}/_runs/${f.name}`).then(parseRun, () => null)
          if (run) runs.push(run)
        }
        for (const f of files.filter(x => x.name.endsWith('.lock'))) {
          const lock = await fs.read(`${base}/_runs/${f.name}`).then(parseLock, () => null)
          if (lock) locks.push(lock)
        }
      } else if (/^\d{3}-/.test(entry.name) && jobs.length < MAX_JOBS) {
        const job = await fs.read(`${base}/${entry.name}/job.json`).then(parseJob, () => null)
        if (job) jobs.push(job)
      }
    }
  }
  return { runs, jobs, locks }
}

export type Doc = { name: string; text: string }
export type Backlog = { openPlans: number; unplannedSpecs: number }

const CLOSED_STATUS = /^status:\s*["']?(completed|done|shipped|superseded|abandoned|cancelled)\b/im

function planIsOpen(text: string): boolean {
  const front = /^---\n([\s\S]*?)\n---/.exec(text)
  if (front && CLOSED_STATUS.test(front[1]!)) return false
  const open = /^\s*- \[ \]/m.test(text)
  const marked = /^\s*- \[[ x-]\]/im.test(text)
  return open || !marked
}

// Counts for the pane: plans with work left, and specs no plan names. A spec that says `Plan: not required`
// in its first lines is a reference and does not count; a plan for the same subject (`x-design.md` -> `x.md`) does.
export function backlogCounts(plans: Doc[], specs: Doc[]): Backlog {
  const blob = plans.map(p => p.text).join('\n')
  const names = new Set(plans.map(p => p.name))
  const unplanned = specs.filter(s => {
    if (blob.includes(s.name)) return false
    if (/^plan:\s*not required/im.test(s.text.split('\n').slice(0, 30).join('\n'))) return false
    return !names.has(s.name.replace(/-(design|review|gate|spec)\.md$/, '.md'))
  })
  return { openPlans: plans.filter(p => planIsOpen(p.text)).length, unplannedSpecs: unplanned.length }
}

export function backlogText(b: Backlog): string {
  if (b.openPlans === 0 && b.unplannedSpecs === 0) return ''
  const plans = `${b.openPlans} open plan${b.openPlans === 1 ? '' : 's'}`
  const specs = `${b.unplannedSpecs} unplanned spec${b.unplannedSpecs === 1 ? '' : 's'}`
  return `${plans} · ${specs}`
}

// Reads the plans and specs of the working folder (the usual superpowers locations). Unreadable files are skipped.
export async function scanBacklog(fs: Fs): Promise<Backlog> {
  const load = async (dir: string): Promise<Doc[]> => {
    let entries: { name: string; kind: string }[] = []
    try {
      entries = await fs.list(dir)
    } catch {
      return []
    }
    const docs: Doc[] = []
    for (const e of entries.filter(x => x.kind !== 'dir' && x.name.endsWith('.md'))) {
      const text = await fs.read(`${dir}/${e.name}`).catch(() => null)
      if (text !== null) docs.push({ name: e.name, text })
    }
    return docs
  }
  return backlogCounts(await load('docs/superpowers/plans'), await load('docs/superpowers/specs'))
}

export const STAGE_STEPS = 5

// Where a job sits on a five-step track: spec, build, review, approve, landed.
export function stageStep(job: Job): number {
  switch (job.stage) {
    case 'spec':
      return 1
    case 'build':
    case 'waiting-input':
      return 2
    case 'review':
      return 3
    case 'approve':
      return 4
    case 'needs-human':
      return job.round > 0 ? 4 : 2
    default:
      return 5
  }
}

const TIER_COLORS: Record<string, string> = { light: '#3fb97c', medium: '#4f7cff', careful: '#e0a526', heavy: '#e5675c', fable: '#b56cf0' }

export function tierColor(tier: string): string {
  return TIER_COLORS[tier] ?? TIER_COLORS.medium!
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = String(total % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

// A live job counts up to now; a landed one stops at its last update.
export function jobElapsed(job: Job, now: number): number | null {
  if (job.started === null) return null
  const end = LANDED.includes(job.stage) && job.updated !== null ? job.updated : now
  return Math.max(0, end - job.started)
}

// From the first start to now, or to the last landing once every job has landed.
export function planElapsed(view: PlanView, now: number): number | null {
  const jobs = [...view.running, ...view.waiting, ...view.finished]
  const starts = jobs.map(j => j.started).filter((t): t is number => t !== null)
  if (starts.length === 0) return null
  const first = Math.min(...starts)
  const allLanded = view.running.length === 0 && view.waiting.length === 0 && view.finished.length > 0
  const ends = view.finished.map(j => j.updated).filter((t): t is number => t !== null)
  const end = allLanded && ends.length > 0 ? Math.max(...ends) : now
  return Math.max(0, end - first)
}

// A bar whose label is written across it: the part under the fill and the part past it,
// so the label reads as text inside the bar. A label that does not fit is cut with an ellipsis.
export function labeledBar(label: string, done: number, total: number, width: number): { filled: string; empty: string } {
  let text = ` ${label} `
  if (text.length > width) text = `${text.slice(0, Math.max(0, width - 2))}… `
  text = text.padEnd(width).slice(0, width)
  const filled = total <= 0 ? 0 : Math.min(width, Math.max(0, Math.round((width * done) / total)))
  return { filled: text.slice(0, filled), empty: text.slice(filled) }
}

export function reviewerLabel(name: string): string {
  return name === 'security' ? 'sec' : name
}

// A cue besides color for a reviewer badge: `!` for requested changes, `…` while nothing came back yet.
export function verdictMark(verdict: string | undefined): string {
  return verdict === 'PASS' ? '' : verdict === 'CHANGES' ? '!' : '…'
}

// `clay:reviewer-ux` -> `ux`, `clay:builder` -> `builder`.
export function roleOf(subagentType: string): string {
  return subagentType.slice(subagentType.lastIndexOf(':') + 1).replace(/^reviewer-/, '')
}

// Every prompt the run command sends starts with the job's folder, which holds its id.
export function jobIdFromPrompt(prompt: string): string | null {
  return /factory\/jobs\/(\d{3}-[^/\s]+)\//.exec(prompt)?.[1] ?? null
}

export function shortModel(id: string): string {
  return id.replace(/^claude-/, '').replace(/-\d{8}$/, '')
}

const sameModel = (asked: string, seen: string) => {
  const a = asked.toLowerCase()
  const b = seen.toLowerCase()
  return b.includes(a) || a.includes(b)
}

// Who has the job right now, with the model they run on. `observed` is what the engine reported at spawn.
export function workingNow(job: Job, observed: Record<string, { model: string }> = {}): { text: string; mismatch: boolean } {
  let roles: string[] = []
  if (job.stage === 'spec' || job.stage === 'build' || job.stage === 'waiting-input') roles = ['builder']
  else if (job.stage === 'approve') roles = ['approver']
  else if (job.stage === 'review') roles = job.reviewers.filter(r => job.reviews[r] !== 'PASS' && job.reviews[r] !== 'CHANGES')

  const groups = new Map<string, string[]>()
  let mismatch = false
  for (const role of roles) {
    const asked = job.agents[role] ?? (role === 'ui' || role === 'ux' ? job.agents.uiux : undefined)
    const seen = (observed[role] ?? (role === 'ui' || role === 'ux' ? observed.uiux : undefined))?.model
    const differs = Boolean(asked && seen && !sameModel(asked.model, seen))
    mismatch = mismatch || differs
    const model = seen ? shortModel(seen) : asked?.model
    const key = model ? `${model}${asked?.effort ? ` ${asked.effort}` : ''}${differs ? ` (asked ${asked!.model})` : ''}` : ''
    groups.set(key, [...(groups.get(key) ?? []), role])
  }
  const text = [...groups].map(([key, who]) => (key ? `${who.join(', ')} · ${key}` : who.join(', '))).join(' · ')
  return { text, mismatch }
}

export type TaskRow = { n: number; title: string; job: Job | null; planned: PlanTask | null }

// One row per task of the plan, in plan order: the job that carries it, or the task itself while it is only planned.
// Jobs that no task list explains (an ad hoc task, or a run file without tasks) follow, by id.
export function taskRows(view: PlanView): TaskRow[] {
  const jobs = [...view.waiting, ...view.running, ...view.finished]
  const byTask = new Map<number, Job>()
  for (const j of jobs) if (j.task > 0 && !byTask.has(j.task)) byTask.set(j.task, j)

  const rows: TaskRow[] = []
  const used = new Set<string>()
  for (const t of [...view.tasks].sort((a, b) => a.n - b.n)) {
    const job = byTask.get(t.n) ?? null
    if (job) used.add(job.id)
    rows.push({ n: t.n, title: t.title, job, planned: job ? null : t })
  }
  for (const j of jobs.filter(x => !used.has(x.id)).sort((a, b) => a.id.localeCompare(b.id))) {
    rows.push({ n: j.task, title: j.id, job: j, planned: null })
  }
  return rows
}

// One sentence for the top of the pane: what needs the user first, then what is moving.
export function situationText(summary: Summary): string {
  const planned = summary.plans.reduce((n, p) => n + p.planned.length, 0)
  const landed = summary.plans.reduce((n, p) => n + p.finished.length, 0)
  const parts = [
    summary.waiting > 0 ? `${summary.waiting} waiting for you` : '',
    summary.running > 0 ? `${summary.running} running` : '',
    planned > 0 ? `${planned} planned` : '',
    landed > 0 ? `${landed} landed` : '',
  ].filter(Boolean)
  return parts.length > 0 ? parts.join(' · ') : 'nothing running'
}

export function rowStatus(row: TaskRow): { label: string; kind: 'waiting' | 'running' | 'landed' | 'planned' } {
  if (!row.job) {
    const after = row.planned?.after ?? []
    return { label: after.length > 0 ? `planned · after ${after.join(', ')}` : 'planned', kind: 'planned' }
  }
  if (LANDED.includes(row.job.stage)) return { label: 'landed', kind: 'landed' }
  if (NEEDS_USER.includes(row.job.stage)) return { label: phaseLabel(row.job), kind: 'waiting' }
  return { label: phaseLabel(row.job), kind: 'running' }
}

// `950`, `9.5k`, `14k`, `1.3M`: short enough for a row of the pane.
export function formatTokens(n: number): string {
  if (n < 1000) return String(Math.max(0, Math.round(n)))
  if (n < 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`
  if (n < 1_000_000) return `${Math.round(n / 1000)}k`
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
}

export function parseLock(text: string): Lock | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!isRecord(raw) || typeof raw.plan !== 'string' || typeof raw.run_id !== 'string') return null
  return {
    plan: raw.plan,
    runId: raw.run_id,
    since: toMs(raw.started) ?? 0,
    heartbeat: toMs(raw.heartbeat) ?? 0,
    protect: Array.isArray(raw.protect) ? raw.protect.filter((p): p is string => typeof p === 'string') : [],
  }
}

export function isStale(lock: Lock, now: number): boolean {
  return now - lock.heartbeat > STALE_MS
}

// The fresh lock whose plan or spec an edit of `path` would change, if any. Paths are compared by their end, since a lock
// names them relative to the repository and an edit names them absolutely.
export function protectedBy(locks: Lock[], path: string, now: number): Lock | null {
  const norm = path.replace(/\\/g, '/')
  return locks.find(l => !isStale(l, now) && l.protect.some(p => norm === p || norm.endsWith(`/${p}`))) ?? null
}

export function lockNote(lock: Lock, now: number): string {
  return isStale(lock, now) ? 'lock stale: no activity for over 30 minutes' : `locked: plan and spec read-only while this run lasts`
}
