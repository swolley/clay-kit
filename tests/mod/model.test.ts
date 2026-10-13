import { test } from 'node:test'
import assert from 'node:assert/strict'

import { parseJob, parseRun, summarize, bar, phaseLabel, waitingIds, scan, activePlans, barParts, waitingLabel } from '../../plugins/factory/hooks/model.ts'

const job = (over: Record<string, unknown> = {}) =>
  parseJob(JSON.stringify({ id: '001-a', plan: 'p1', repo: 'api', tier: 'medium', stage: 'build', round: 0, reviewers: [], reviews: {}, ...over }))!

test('parseJob accepts a valid job and rejects garbage', () => {
  assert.equal(job().id, '001-a')
  assert.equal(parseJob('{nope'), null)
  assert.equal(parseJob(JSON.stringify({ id: 'x', stage: 'build' })), null)
  assert.equal(parseJob(JSON.stringify({ id: '001-a', plan: 'p', stage: 'dancing' })), null)
})

test('parseRun reads totals and tolerates missing fields', () => {
  assert.deepEqual(parseRun(JSON.stringify({ plan: 'p1', total: 5, done: 2 })), { plan: 'p1', total: 5, done: 2 })
  assert.deepEqual(parseRun(JSON.stringify({ plan: 'p1' })), { plan: 'p1', total: 0, done: 0 })
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
  const s = summarize([{ plan: 'p1', total: 6, done: 0 }], jobs)
  assert.equal(s.plans.length, 1)
  assert.deepEqual([s.plans[0]!.total, s.plans[0]!.done], [6, 2])
  assert.equal(s.plans[0]!.running.length, 1)
  assert.equal(s.waiting, 2)
  assert.equal(s.running, 1)
})

test('summarize trusts a larger done from the run file and falls back to the job count for total', () => {
  const a = summarize([{ plan: 'p1', total: 5, done: 3 }], [job({ stage: 'merged' })])
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
  assert.deepEqual(out.runs, [{ plan: 'p1', total: 4, done: 1 }])
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
