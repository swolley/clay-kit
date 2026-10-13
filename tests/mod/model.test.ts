import { test } from 'node:test'
import assert from 'node:assert/strict'

import { parseJob, parseRun, summarize, bar, phaseLabel, waitingIds, scan, activePlans, barParts, waitingLabel, percent, stageStep, tierColor, formatDuration, jobElapsed, planElapsed } from '../../plugins/factory/hooks/model.ts'

const job = (over: Record<string, unknown> = {}) =>
  parseJob(JSON.stringify({ id: '001-a', plan: 'p1', repo: 'api', tier: 'medium', stage: 'build', round: 0, reviewers: [], reviews: {}, ...over }))!

test('parseJob accepts a valid job and rejects garbage', () => {
  assert.equal(job().id, '001-a')
  assert.equal(parseJob('{nope'), null)
  assert.equal(parseJob(JSON.stringify({ id: 'x', stage: 'build' })), null)
  assert.equal(parseJob(JSON.stringify({ id: '001-a', plan: 'p', stage: 'dancing' })), null)
})

test('parseRun reads totals and tolerates missing fields', () => {
  assert.deepEqual(parseRun(JSON.stringify({ plan: 'p1', total: 5, done: 2 })), { plan: 'p1', total: 5, done: 2, tasks: [] })
  assert.deepEqual(parseRun(JSON.stringify({ plan: 'p1' })), { plan: 'p1', total: 0, done: 0, tasks: [] })
  assert.equal(parseRun('[]'), null)
})

test('summarize counts landed jobs as done and splits running from waiting', () => {
  const jobs = [
    job({ id: '001-a', stage: 'merged' }),
    job({ id: '002-b', stage: 'committed' }),
    job({ id: '003-c', stage: 'review', round: 1 }),
    job({ id: '004-d', stage: 'needs-human' }),
    job({ id: '005-e', stage: 'waiting-input' }),
  ]
  const s = summarize([{ plan: 'p1', total: 6, done: 0, tasks: [] }], jobs)
  assert.equal(s.plans.length, 1)
  assert.deepEqual([s.plans[0]!.total, s.plans[0]!.done], [6, 2])
  assert.equal(s.plans[0]!.running.length, 1)
  assert.equal(s.waiting, 2)
  assert.equal(s.running, 1)
})

test('summarize trusts a larger done from the run file and falls back to the job count for total', () => {
  const a = summarize([{ plan: 'p1', total: 5, done: 3, tasks: [] }], [job({ stage: 'merged' })])
  assert.equal(a.plans[0]!.done, 3)
  const b = summarize([], [job({ id: '001-a', stage: 'build' }), job({ id: '002-b', stage: 'merged' })])
  assert.deepEqual([b.plans[0]!.total, b.plans[0]!.done], [2, 1])
})

test('summarize groups by plan and skips plans with nothing to show', () => {
  const s = summarize([], [job({ plan: 'p1', stage: 'merged' }), job({ id: '002-b', plan: 'p2', stage: 'build' })])
  assert.deepEqual(s.plans.map(p => p.plan).sort(), ['p1', 'p2'])
})

test('bar draws a fixed-width bar and handles zero total', () => {
  assert.equal(bar(0, 4, 8), '░░░░░░░░')
  assert.equal(bar(2, 4, 8), '████░░░░')
  assert.equal(bar(4, 4, 8), '████████')
  assert.equal(bar(1, 0, 8), '')
  assert.equal(bar(9, 4, 8), '████████')
})

test('phaseLabel names the stage and shows review progress', () => {
  assert.equal(phaseLabel(job({ stage: 'build' })), 'build')
  const r = job({ stage: 'review', round: 2, reviewers: ['code', 'ux'], reviews: { code: 'PASS', ux: 'pending' } })
  assert.equal(phaseLabel(r), 'review r2 1/2')
  assert.equal(phaseLabel(job({ stage: 'waiting-input' })), 'waiting for you')
})

test('waitingIds lists jobs that need the user, for toasts on change', () => {
  const ids = waitingIds([job({ id: '001-a', stage: 'needs-human' }), job({ id: '002-b', stage: 'build' }), job({ id: '003-c', stage: 'waiting-input' })])
  assert.deepEqual([...ids].sort(), ['001-a', '003-c'])
})


// A flat map of file paths stands in for the disk.
const fakeFs = (files: Record<string, string>) => ({
  async list(path = '.') {
    const prefix = path === '.' ? '' : path.replace(/\/$/, '') + '/'
    const seen = new Map<string, 'file' | 'dir'>()
    for (const p of Object.keys(files)) {
      if (!p.startsWith(prefix)) continue
      const rest = p.slice(prefix.length)
      const [head, ...tail] = rest.split('/')
      if (head) seen.set(head, tail.length ? 'dir' : 'file')
    }
    if (seen.size === 0 && path !== '.') throw new Error('ENOENT')
    return [...seen].map(([name, kind]) => ({ name, kind }))
  },
  async read(path: string) {
    if (!(path in files)) throw new Error('ENOENT')
    return files[path]!
  },
  async exists(path: string) {
    return Object.keys(files).some(p => p === path || p.startsWith(path.replace(/\/$/, '') + '/'))
  },
})

const J = (id: string, stage: string, plan = 'p1') => JSON.stringify({ id, plan, stage, round: 0, reviewers: [], reviews: {} })

test('scan reads jobs and run files from the working folder', async () => {
  const fs = fakeFs({
    'factory/jobs/001-a/job.json': J('001-a', 'build'),
    'factory/jobs/002-b/job.json': J('002-b', 'merged'),
    'factory/jobs/_runs/p1.json': JSON.stringify({ plan: 'p1', total: 4, done: 1 }),
    'factory/jobs/dashboard.html': '<html>',
  })
  const out = await scan(fs)
  assert.deepEqual(out.jobs.map(j => j.id).sort(), ['001-a', '002-b'])
  assert.deepEqual(out.runs, [{ plan: 'p1', total: 4, done: 1, tasks: [] }])
})

test('scan also looks one folder down, as when started from a workspace root', async () => {
  const fs = fakeFs({
    'api/factory/jobs/001-a/job.json': J('001-a', 'review'),
    'ui/factory/jobs/001-z/job.json': J('001-z', 'build', 'p2'),
    'node_modules/x/factory/jobs/001-q/job.json': J('001-q', 'build'),
    '.hidden/factory/jobs/001-h/job.json': J('001-h', 'build'),
  })
  const out = await scan(fs)
  assert.deepEqual(out.jobs.map(j => j.id).sort(), ['001-a', '001-z'])
})

test('scan survives bad files and returns nothing when there is no factory folder', async () => {
  const bad = fakeFs({ 'factory/jobs/001-a/job.json': '{broken', 'factory/jobs/002-b/job.json': J('002-b', 'build') })
  assert.deepEqual((await scan(bad)).jobs.map(j => j.id), ['002-b'])
  const none = await scan(fakeFs({ 'src/a.ts': 'x' }))
  assert.deepEqual(none, { runs: [], jobs: [] })
})


test('activePlans keeps only plans with running or waiting jobs, in order of need', () => {
  const s = summarize([], [
    job({ id: '001-a', plan: 'finished', stage: 'merged' }),
    job({ id: '002-b', plan: 'busy', stage: 'build' }),
    job({ id: '003-c', plan: 'stuck', stage: 'needs-human' }),
  ])
  assert.deepEqual(activePlans(s).map(p => p.plan), ['stuck', 'busy'])
})

test('activePlans is empty when everything has landed', () => {
  assert.deepEqual(activePlans(summarize([], [job({ stage: 'merged' })])), [])
})

test('barParts splits a bar into its filled and empty halves', () => {
  assert.deepEqual(barParts(1, 5, 10), { filled: '██', empty: '░░░░░░░░' })
  assert.deepEqual(barParts(0, 5, 10), { filled: '', empty: '░░░░░░░░░░' })
  assert.deepEqual(barParts(5, 5, 10), { filled: '██████████', empty: '' })
  assert.deepEqual(barParts(1, 0, 10), { filled: '', empty: '' })
})

test('waitingLabel names the jobs that need the user and trims long lists', () => {
  const mk = (n: number) => summarize([], Array.from({ length: n }, (_, i) => job({ id: `00${i + 1}-x`, stage: i % 2 ? 'waiting-input' : 'needs-human' })))
  assert.equal(waitingLabel(mk(0)), '')
  assert.equal(waitingLabel(mk(2)), '001-x, 002-x')
  assert.equal(waitingLabel(mk(5), 3), '001-x, 002-x, 003-x +2')
})


const T0 = Date.parse('2026-10-13T10:00:00Z')
const iso = (ms: number) => new Date(ms).toISOString()

test('parseJob reads task number and timestamps, and tolerates their absence', () => {
  const j = job({ task: 3, started: iso(T0), updated: iso(T0 + 5000) })
  assert.deepEqual([j.task, j.started, j.updated], [3, T0, T0 + 5000])
  const bare = job()
  assert.deepEqual([bare.task, bare.started, bare.updated], [0, null, null])
})

test('parseRun reads the planned tasks', () => {
  const r = parseRun(JSON.stringify({ plan: 'p1', total: 3, done: 0, tasks: [{ n: 1, title: 'A', tier: 'light', after: [] }, { n: 2, title: 'B', tier: 'heavy', after: [1] }, { bad: true }] }))!
  assert.deepEqual(r.tasks, [{ n: 1, title: 'A', tier: 'light', after: [] }, { n: 2, title: 'B', tier: 'heavy', after: [1] }])
})

test('summarize puts landed jobs in finished and not-yet-started tasks in planned', () => {
  const run = parseRun(JSON.stringify({ plan: 'p1', total: 4, done: 0, tasks: [1, 2, 3, 4].map(n => ({ n, title: `T${n}`, tier: 'medium', after: [] })) }))!
  const s = summarize([run], [job({ id: '001-a', task: 1, stage: 'merged' }), job({ id: '002-b', task: 2, stage: 'build' })])
  const p = s.plans[0]!
  assert.deepEqual(p.finished.map(j => j.id), ['001-a'])
  assert.deepEqual(p.planned.map(t => t.n), [3, 4])
  assert.equal(p.total, 4)
})

test('percent rounds and guards a zero total', () => {
  assert.equal(percent(1, 5), 20)
  assert.equal(percent(1, 3), 33)
  assert.equal(percent(0, 0), 0)
  assert.equal(percent(9, 4), 100)
})

test('stageStep places a job on a five-step track', () => {
  assert.equal(stageStep(job({ stage: 'spec' })), 1)
  assert.equal(stageStep(job({ stage: 'build' })), 2)
  assert.equal(stageStep(job({ stage: 'waiting-input' })), 2)
  assert.equal(stageStep(job({ stage: 'review' })), 3)
  assert.equal(stageStep(job({ stage: 'approve' })), 4)
  assert.equal(stageStep(job({ stage: 'merged' })), 5)
  assert.equal(stageStep(job({ stage: 'needs-human', round: 1 })), 4)
  assert.equal(stageStep(job({ stage: 'needs-human', round: 0 })), 2)
})

test('tierColor gives each tier its own color and a fallback', () => {
  const colors = ['light', 'medium', 'careful', 'heavy', 'fable'].map(tierColor)
  assert.equal(new Set(colors).size, 5)
  assert.equal(tierColor('unknown'), tierColor('medium'))
})

test('formatDuration prints m:ss and h:mm:ss', () => {
  assert.equal(formatDuration(26_000), '0:26')
  assert.equal(formatDuration(725_000), '12:05')
  assert.equal(formatDuration(3_725_000), '1:02:05')
  assert.equal(formatDuration(-5), '0:00')
})

test('jobElapsed runs until now for live jobs and stops at the last update for landed ones', () => {
  const live = job({ stage: 'build', started: iso(T0), updated: iso(T0 + 1000) })
  assert.equal(jobElapsed(live, T0 + 60_000), 60_000)
  const done = job({ stage: 'merged', started: iso(T0), updated: iso(T0 + 90_000) })
  assert.equal(jobElapsed(done, T0 + 999_000), 90_000)
  assert.equal(jobElapsed(job(), T0), null)
})

test('planElapsed spans from the first start to now, or to the last landing when all landed', () => {
  const a = job({ id: '001-a', stage: 'merged', started: iso(T0), updated: iso(T0 + 60_000) })
  const b = job({ id: '002-b', stage: 'build', started: iso(T0 + 30_000), updated: iso(T0 + 40_000) })
  assert.equal(planElapsed(summarize([], [a, b]).plans[0]!, T0 + 120_000), 120_000)
  assert.equal(planElapsed(summarize([], [a]).plans[0]!, T0 + 999_000), 60_000)
  assert.equal(planElapsed(summarize([], [job()]).plans[0]!, T0), null)
})
