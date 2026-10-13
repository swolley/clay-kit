import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import {
  STAGE_STEPS,
  activePlans,
  formatDuration,
  jobElapsed,
  labeledBar,
  phaseLabel,
  planElapsed,
  reviewerLabel,
  scan,
  stageStep,
  summarize,
  tierColor,
  verdictMark,
  waitingIds,
  waitingLabel,
} from './model'
import type { Fs, Job, PlanView, Summary } from './model'

const PANE = 'factory-agents'
const POLL_MS = 3000

const view = atom({ plugin: 'factory', key: 'view' } as const, { plans: [], waiting: 0, running: 0 } as Summary)
const isHidden = atom({ plugin: 'factory', key: 'isHidden' } as const, false)
const isFinishedOpen = atom({ plugin: 'factory', key: 'isFinishedOpen' } as const, false)

const verdictBackground = (verdict: string | undefined) => (verdict === 'PASS' ? '#3fb97c' : verdict === 'CHANGES' ? '#e5675c' : '#4a5163')

// Plans that need the user first, then the ones running, then the rest.
const byNeed = (a: PlanView, b: PlanView) => b.waiting.length - a.waiting.length || b.running.length - a.running.length

const TRACK = '#343a48'
const OK = '#3fb97c'
const WAIT = '#f2c230'

const INK = '#0c0f15'
// Round ends for bars and badges. If the font draws them badly, set both to '' to get square ends.
const CAP_L = '◖'
const CAP_R = '◗'
const SOFT = '#d8dde8'

// A solid bar with its label written inside it: the part under the fill and the part past it are two
// text runs with a background color each, so it draws as one strip on every surface.
// `Box` and `Text` are the surface's own elements, resolved by the caller.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const labeled = (Box: any, Text: any, label: string, done: number, total: number, width: number, color: string) => {
  const parts = labeledBar(label, done, total, width)
  const left = parts.filled.length > 0 ? color : TRACK
  const right = parts.empty.length > 0 ? TRACK : color
  return (
    <Box flexShrink={0}>
      {CAP_L && <Text color={left}>{CAP_L}</Text>}
      {parts.filled.length > 0 && <Text bold color={INK} backgroundColor={color}>{parts.filled}</Text>}
      {parts.empty.length > 0 && <Text color={SOFT} backgroundColor={TRACK}>{parts.empty}</Text>}
      {CAP_R && <Text color={right}>{CAP_R}</Text>}
    </Box>
  )
}

const stateIcon = (job: Job) => (job.stage === 'merged' || job.stage === 'committed' ? '✓' : '●')

const stateColor = (job: Job) =>
  job.stage === 'merged' || job.stage === 'committed' ? OK : job.stage === 'needs-human' || job.stage === 'waiting-input' ? WAIT : tierColor(job.tier)

// A reviewer as a small colored badge: the color is the verdict, the mark is the cue besides color.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const badge = (Box: any, Text: any, name: string, verdict: string | undefined) => {
  const color = verdictBackground(verdict)
  return (
    <Box flexShrink={0}>
      {CAP_L && <Text color={color}>{CAP_L}</Text>}
      <Text bold color={INK} backgroundColor={color}>{`${reviewerLabel(name)}${verdictMark(verdict)}`}</Text>
      {CAP_R && <Text color={color}>{CAP_R}</Text>}
    </Box>
  )
}

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

    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    const active = activePlans(summary)
    const lead = active[0]
    if (!lead) return next(e)
    const more = active.length > 1 ? ` +${active.length - 1}` : ''
    const phases = [...new Set(lead.running.map(phaseLabel))].join(', ')
    const label = `Tasks ${lead.done}/${lead.total}${phases ? ` · ${phases}` : ''}`
    const dot = summary.waiting > 0 ? WAIT : OK

    // One row, never wrapped. The time stays in the pane.
    return (
      <Box flexWrap="nowrap" gap={1}>
        <Text bold color={dot}>●</Text>
        <Text bold>{lead.plan.slice(0, 20)}{more}</Text>
        {labeled(Box, Text, label, lead.done, lead.total, 46, OK)}
        {summary.waiting > 0 && <Text bold color={WAIT}>waiting: {waitingLabel(summary, 1)}</Text>}
        <Text dimColor>×{summary.running}</Text>
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
        <Box flexDirection="column">
          <Box gap={1}>
            <Text color={color}>{stateIcon(job)}</Text>
            <Text bold={job.stage === 'needs-human' || job.stage === 'waiting-input'}>{job.id}</Text>
            <Text color={tierColor(job.tier)}>{job.tier}</Text>
            <Text dimColor>{spent === null ? '' : formatDuration(spent)}</Text>
          </Box>
          <Box gap={1} paddingLeft={2}>
            {labeled(Box, Text, phaseLabel(job), stageStep(job), STAGE_STEPS, 30, color)}
            {job.reviewers.map(r => badge(Box, Text, r, job.reviews[r]))}
          </Box>
        </Box>
      )
    }

    const tile = (label: string, value: string, color?: string) => (
      <Box flexDirection="column" borderStyle="round" borderColor={TRACK} paddingX={1} minWidth={14}>
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
            {labeled(Box, Text, `Tasks ${p.done}/${p.total}`, p.done, p.total, 30, OK)}
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
        <Box gap={1}>
          <Text dimColor>reviewers</Text>
          {badge(Box, Text, 'pass', 'PASS')}
          {badge(Box, Text, 'changes', 'CHANGES')}
          {badge(Box, Text, 'pending', 'pending')}
        </Box>
        {[...summary.plans].sort(byNeed).map(plan)}
      </Box>
    )
  })
}
