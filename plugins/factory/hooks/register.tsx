import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import {
  STAGE_STEPS,
  activePlans,
  barParts,
  formatDuration,
  jobElapsed,
  percent,
  phaseLabel,
  planElapsed,
  scan,
  stageStep,
  summarize,
  tierColor,
  waitingIds,
  waitingLabel,
} from './model'
import type { Fs, Job, PlanView, Summary } from './model'

const PANE = 'factory-agents'
const POLL_MS = 3000

const view = atom({ plugin: 'factory', key: 'view' } as const, { plans: [], waiting: 0, running: 0 } as Summary)
const isHidden = atom({ plugin: 'factory', key: 'isHidden' } as const, false)
const isFinishedOpen = atom({ plugin: 'factory', key: 'isFinishedOpen' } as const, false)

const verdictColor = (verdict: string | undefined) => (verdict === 'PASS' ? 'green' : verdict === 'CHANGES' ? 'red' : undefined)

// Plans that need the user first, then the ones running, then the rest.
const byNeed = (a: PlanView, b: PlanView) => b.waiting.length - a.waiting.length || b.running.length - a.running.length

const TRACK = '#343a48'
const TILE = '#232834'
const OK = '#3fb97c'
const WAIT = '#f2c230'

// A solid bar made of two filled boxes, so it draws as one smooth strip on every surface.
// `Box` is the surface's own element, resolved by the caller.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const meter = (Box: any, done: number, total: number, width: number, color: string) => {
  const parts = barParts(done, total, width)
  return (
    <Box width={width} height={1} flexShrink={0}>
      {parts.filled.length > 0 && <Box width={parts.filled.length} height={1} backgroundColor={color} />}
      {parts.empty.length > 0 && <Box width={parts.empty.length} height={1} backgroundColor={TRACK} />}
    </Box>
  )
}

const stateIcon = (job: Job) => (job.stage === 'merged' || job.stage === 'committed' ? '✓' : '●')

const stateColor = (job: Job) =>
  job.stage === 'merged' || job.stage === 'committed' ? OK : job.stage === 'needs-human' || job.stage === 'waiting-input' ? WAIT : tierColor(job.tier)

export const register: Register = on => {
  let timer: { cancel: () => void } | undefined
  let known: Set<string> | null = null

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'factory-progress', description: 'Show or hide the factory progress band' })
    await $.command.register({ name: 'factory-agents', description: 'Open or close the pane with the factory jobs' })

    const fs: Fs = {
      list: path => $.fs.list(path),
      read: async path => {
        const text = await $.fs.read(path)
        return typeof text === 'string' ? text : ''
      },
      exists: path => $.fs.exists(path),
    }

    const refresh = async () => {
      try {
        const found = await scan(fs)
        const summary = summarize(found.runs, found.jobs)
        await update($, view, () => summary)

        const now = waitingIds(found.jobs)
        const fresh = [...now].filter(id => !known || !known.has(id))
        if (fresh.length > 0) {
          $.ui.toast(known ? `${fresh.join(', ')} needs you` : `${now.size} factory job(s) waiting for you`)
        }
        known = now
      } catch {
        // A scan that fails shows the previous state until the next tick.
      }
    }

    timer?.cancel()
    await refresh()
    timer = $.clock.every(POLL_MS, () => void refresh())

    return next(e)
  })

  on('command.run', { command: 'factory-progress' }, async $ => {
    const hidden = await read($, isHidden)
    await update($, isHidden, () => !hidden)
    return { text: hidden ? 'Factory progress band shown.' : 'Factory progress band hidden.' }
  })

  on('command.run', { command: 'factory-agents' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Factory jobs' })
    return { text: 'Factory jobs pane opened.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const summary = await read($, view)
    const quiet = e.props.hasSurvey || (await read($, isHidden)) || (summary.running === 0 && summary.waiting === 0)
    if (quiet) return next(e)

    const { Box, Button, Text } = $.ui.resolve(e)
    const active = activePlans(summary)
    const lead = active[0]
    if (!lead) return next(e)
    const now = await $.clock.now()
    const more = active.length > 1 ? ` +${active.length - 1}` : ''
    const phases = [...new Set(lead.running.map(phaseLabel))].join(', ')
    const elapsed = planElapsed(lead, now)
    const detail = [lead.plan.slice(0, 22) + more, elapsed === null ? '' : formatDuration(elapsed), phases].filter(Boolean).join(' · ')

    // One row, never wrapped: the long parts truncate instead.
    return (
      <Box flexWrap="nowrap" gap={1}>
        <Text bold>factory</Text>
        {meter(Box, lead.done, lead.total, 12, OK)}
        <Text bold>{lead.done}/{lead.total}</Text>
        <Text>{percent(lead.done, lead.total)}%</Text>
        <Box flexShrink={1}>
          <Text dimColor wrap="truncate-end">{detail}</Text>
        </Box>
        {summary.waiting > 0 && (
          <Box flexShrink={0}>
            <Text bold color={WAIT}>waiting: {waitingLabel(summary, 1)}</Text>
          </Box>
        )}
        <Button key="hide" label="×" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const summary = await read($, view)
    if (summary.plans.length === 0) return <Text dimColor>No factory jobs found here.</Text>
    const now = await $.clock.now()
    const isOpen = await read($, isFinishedOpen)

    const jobLine = (job: Job) => {
      const spent = jobElapsed(job, now)
      const color = stateColor(job)
      return (
        <Box gap={1}>
          <Text color={color}>{stateIcon(job)}</Text>
          <Text bold={job.stage === 'needs-human' || job.stage === 'waiting-input'}>{job.id}</Text>
          <Text color={tierColor(job.tier)}>{job.tier}</Text>
          {meter(Box, stageStep(job), STAGE_STEPS, 8, color)}
          <Text dimColor>{phaseLabel(job)}{spent === null ? '' : ` · ${formatDuration(spent)}`}</Text>
          {job.reviewers.map(r => (
            <Text color={verdictColor(job.reviews[r])}>{r}:{job.reviews[r] ?? 'pending'}</Text>
          ))}
        </Box>
      )
    }

    const tile = (label: string, value: string, color?: string) => (
      <Box flexDirection="column" backgroundColor={TILE} paddingX={1} minWidth={14}>
        <Text dimColor>{label}</Text>
        <Text bold color={color}>{value}</Text>
      </Box>
    )

    const plan = (p: PlanView) => {
      const elapsed = planElapsed(p, now)
      return (
        <Box flexDirection="column">
          <Box gap={1}>
            <Text bold>{p.plan}</Text>
            {meter(Box, p.done, p.total, 16, OK)}
            <Text bold>{p.done}/{p.total}</Text>
            <Text>{percent(p.done, p.total)}%</Text>
            <Text dimColor>{elapsed === null ? '' : formatDuration(elapsed)}</Text>
          </Box>
          {p.waiting.length > 0 && <Text bold color={WAIT}>Waiting for you · {p.waiting.length}</Text>}
          {p.waiting.map(jobLine)}
          {p.running.length > 0 && <Text bold>Running · {p.running.length}</Text>}
          {p.running.map(jobLine)}
          {p.finished.length > 0 && (
            <Button key={`fin-${p.plan}`} label={`${isOpen ? '▾' : '▸'} Finished · ${p.finished.length}`} onPress={() => update($, isFinishedOpen, () => !isOpen)} />
          )}
          {isOpen && p.finished.map(jobLine)}
          {p.planned.length > 0 && <Text bold>Planned · {p.planned.length}</Text>}
          {p.planned.map(t => (
            <Box gap={1}>
              <Text dimColor>○ {t.n}. {t.title}</Text>
              <Text color={tierColor(t.tier)}>{t.tier}</Text>
              <Text dimColor>{t.after.length > 0 ? `after ${t.after.join(', ')}` : ''}</Text>
            </Box>
          ))}
        </Box>
      )
    }

    const lead = activePlans(summary)[0] ?? summary.plans[0]
    const landed = summary.plans.reduce((n, p) => n + p.done, 0)
    const total = summary.plans.reduce((n, p) => n + p.total, 0)
    const leadElapsed = lead ? planElapsed(lead, now) : null

    return (
      <Box flexDirection="column" gap={1}>
        <Box gap={1}>
          {tile('Running', String(summary.running))}
          {tile('Waiting', String(summary.waiting), summary.waiting > 0 ? WAIT : undefined)}
          {tile('Landed', `${landed}/${total}`, OK)}
          {tile('Elapsed', leadElapsed === null ? '-' : formatDuration(leadElapsed))}
        </Box>
        {[...summary.plans].sort(byNeed).map(plan)}
      </Box>
    )
  })
}
