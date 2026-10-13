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
import { pillBar, tierFill, tilePill } from './svg'

const PANE = 'factory-agents'
const POLL_MS = 3000

const view = atom({ plugin: 'factory', key: 'view' } as const, { plans: [], waiting: 0, running: 0 } as Summary)
const isHidden = atom({ plugin: 'factory', key: 'isHidden' } as const, false)
const isFinishedOpen = atom({ plugin: 'factory', key: 'isFinishedOpen' } as const, false)

const ledColor = (verdict: string | undefined) => (verdict === 'PASS' ? '#3fb97c' : verdict === 'CHANGES' ? '#e5675c' : '#7d879a')

// Plans that need the user first, then the ones running, then the rest.
const byNeed = (a: PlanView, b: PlanView) => b.waiting.length - a.waiting.length || b.running.length - a.running.length

const TRACK = '#343a48'
const OK = '#3fb97c'
const OK_FILL = '#2a8f5f'
const WAIT_FILL = '#a87415'
const WAIT = '#f2c230'

const INK = '#0c0f15'
const SOFT = '#d8dde8'

// A solid bar with its label written inside it: the part under the fill and the part past it are two
// text runs with a background color each, so it draws as one strip on every surface.
// `Box` and `Text` are the surface's own elements, resolved by the caller.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const labeled = (Box: any, Text: any, label: string, done: number, total: number, width: number, color: string) => {
  const parts = labeledBar(label, done, total, width)
  return (
    <Box flexShrink={0}>
      {parts.filled.length > 0 && <Text bold color={INK} backgroundColor={color}>{parts.filled}</Text>}
      {parts.empty.length > 0 && <Text color={SOFT} backgroundColor={TRACK}>{parts.empty}</Text>}
    </Box>
  )
}

const stateIcon = (job: Job) => (job.stage === 'merged' || job.stage === 'committed' ? '✓' : '●')

const stateColor = (job: Job) =>
  job.stage === 'merged' || job.stage === 'committed' ? OK : job.stage === 'needs-human' || job.stage === 'waiting-input' ? WAIT : tierColor(job.tier)

const fillFor = (job: Job) =>
  job.stage === 'merged' || job.stage === 'committed' ? OK_FILL : job.stage === 'needs-human' || job.stage === 'waiting-input' ? WAIT_FILL : tierFill(job.tier)

// A progress bar with its label inside. On surfaces that draw vector art it is a rounded SVG pill; elsewhere the
// bar is built from colored text cells (`cols` wide). `elements` is what `$.ui.resolve` returned.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const bar = (elements: any, label: string, done: number, total: number, px: number, fill: string, glyph: string, cols: number) => {
  const Svg = 'Svg' in elements ? elements.Svg : undefined
  if (!Svg) return labeled(elements.Box, elements.Text, label, done, total, cols, glyph)
  return (
    <Box alignSelf="center" flexShrink={0}>
      <Svg source={pillBar({ label, done, total, width: px, fill, track: TRACK })} alt={label} width={px} height={20} />
    </Box>
  )
}

// A summary tile: a rounded SVG where vector art is drawn, a bordered box elsewhere.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tile = (elements: any, label: string, value: string, color?: string) => {
  const { Box, Text } = elements
  const Svg = 'Svg' in elements ? elements.Svg : undefined
  if (Svg) {
    return (
      <Box alignSelf="center" flexShrink={0}>
        <Svg source={tilePill({ label, value, valueColor: color, bg: '#1b2029', border: TRACK })} alt={`${label} ${value}`} width={118} height={46} />
      </Box>
    )
  }
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={TRACK} paddingX={1} minWidth={14}>
      <Text dimColor>{label}</Text>
      <Text bold color={color}>{value}</Text>
    </Box>
  )
}

// A reviewer as a colored LED with its name beside it. The mark is a cue besides color.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const led = (Box: any, Text: any, name: string, verdict: string | undefined) => (
  <Box flexShrink={0}>
    <Text color={ledColor(verdict)}>●</Text>
    <Text>{` ${reviewerLabel(name)}${verdictMark(verdict)}`}</Text>
  </Box>
)



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
      <Box flexWrap="nowrap" gap={1} alignItems="center">
        <Text bold color={dot}>●</Text>
        <Text bold>{lead.plan.slice(0, 20)}{more}</Text>
        {bar(elements, label, lead.done, lead.total, 340, OK_FILL, OK, 46)}
        {summary.waiting > 0 && <Text bold color={WAIT}>waiting: {waitingLabel(summary, 1)}</Text>}
        <Text dimColor>×{summary.running}</Text>
        <Button key="hide" label="×" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
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
          <Box gap={1} paddingLeft={2} alignItems="center">
            {bar(elements, phaseLabel(job), stageStep(job), STAGE_STEPS, 220, fillFor(job), color, 30)}
            {job.reviewers.map(r => led(Box, Text, r, job.reviews[r]))}
          </Box>
        </Box>
      )
    }

    const plan = (p: PlanView) => {
      const elapsed = planElapsed(p, now)
      return (
        <Box flexDirection="column">
          <Box gap={1} alignItems="center">
            <Text bold>{p.plan}</Text>
            {bar(elements, `Tasks ${p.done}/${p.total}`, p.done, p.total, 220, OK_FILL, OK, 30)}
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
        <Box gap={1} alignItems="center">
          {tile(elements, 'Running', String(summary.running))}
          {tile(elements, 'Waiting', String(summary.waiting), summary.waiting > 0 ? WAIT : undefined)}
          {tile(elements, 'Landed', `${landed}/${total}`, OK)}
          {tile(elements, 'Elapsed', leadElapsed === null ? '-' : formatDuration(leadElapsed))}
        </Box>
        <Box gap={1}>
          <Text dimColor>reviewers</Text>
          {led(Box, Text, 'pass', 'PASS')}
          {led(Box, Text, 'changes', 'CHANGES')}
          {led(Box, Text, 'pending', 'pending')}
        </Box>
        {[...summary.plans].sort(byNeed).map(plan)}
      </Box>
    )
  })
}
