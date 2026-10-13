// Pure helpers for the progress band and pane. No imports from the host, so they can be tested with plain Node.

export type Stage = 'spec' | 'build' | 'waiting-input' | 'review' | 'approve' | 'merged' | 'committed' | 'needs-human'

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
}

export type Run = { plan: string; total: number; done: number; tasks: PlanTask[] }

export type PlanView = {
  plan: string
  total: number
  done: number
  running: Job[]
  waiting: Job[]
  finished: Job[]
  planned: PlanTask[]
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

export function parseJob(text: string): Job | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!isRecord(raw) || typeof raw.id !== 'string' || typeof raw.plan !== 'string' || typeof raw.stage !== 'string') return null
  if (!STAGES.includes(raw.stage)) return null
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
  return { plan: raw.plan, total: typeof raw.total === 'number' ? raw.total : 0, done: typeof raw.done === 'number' ? raw.done : 0, tasks }
}

export function summarize(runs: Run[], jobs: Job[]): Summary {
  const plans = new Map<string, Job[]>()
  for (const job of jobs) plans.set(job.plan, [...(plans.get(job.plan) ?? []), job])
  for (const run of runs) if (!plans.has(run.plan)) plans.set(run.plan, [])

  const views: PlanView[] = []
  for (const [plan, list] of plans) {
    const run = runs.find(r => r.plan === plan)
    const landed = list.filter(j => LANDED.includes(j.stage)).length
    const started = new Set(list.map(j => j.task))
    views.push({
      plan,
      total: run && run.total > 0 ? run.total : run && run.tasks.length > 0 ? run.tasks.length : list.length,
      done: Math.max(run?.done ?? 0, landed),
      running: list.filter(j => !LANDED.includes(j.stage) && !NEEDS_USER.includes(j.stage)),
      waiting: list.filter(j => NEEDS_USER.includes(j.stage)),
      finished: list.filter(j => LANDED.includes(j.stage)),
      planned: (run?.tasks ?? []).filter(t => !started.has(t.n)),
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
export async function scan(fs: Fs): Promise<{ runs: Run[]; jobs: Job[] }> {
  const runs: Run[] = []
  const jobs: Job[] = []
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
      } else if (/^\d{3}-/.test(entry.name) && jobs.length < MAX_JOBS) {
        const job = await fs.read(`${base}/${entry.name}/job.json`).then(parseJob, () => null)
        if (job) jobs.push(job)
      }
    }
  }
  return { runs, jobs }
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
