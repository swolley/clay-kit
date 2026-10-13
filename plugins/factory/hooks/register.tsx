import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import {
  STAGE_STEPS,
  activePlans,
  formatDuration,
  jobIdFromPrompt,
  jobElapsed,
  labeledBar,
  phaseLabel,
  planElapsed,
  reviewerLabel,
  roleOf,
  rowStatus,
  scan,
  stageStep,
  summarize,
  situationText,
  taskRows,
  tierColor,
  verdictMark,
  waitingIds,
  waitingLabel,
  workingNow,
} from './model'
import type { Fs, Job, PlanView, Summary, TaskRow } from './model'
import { pillBar, slimBar } from './svg'

const PANE = 'factory-agents'
const POLL_MS = 3000

const view = atom({ plugin: 'factory', key: 'view' } as const, { plans: [], waiting: 0, running: 0 } as Summary)
const isHidden = atom({ plugin: 'factory', key: 'isHidden' } as const, false)
const isOnlyMine = atom({ plugin: 'factory', key: 'isOnlyMine' } as const, false)
// The model each agent of a job really started on, as the engine reported it at spawn, by job id and role.
const observed = atom({ plugin: 'factory', key: 'observed' } as const, {} as Record<string, Record<string, { model: string }>>)

const ledColor = (verdict: string | undefined) => (verdict === 'PASS' ? '#3fb97c' : verdict === 'CHANGES' ? '#e5675c' : '#7d879a')

// Plans that need the user first, then the ones running, then the rest.
const byNeed = (a: PlanView, b: PlanView) => b.waiting.length - a.waiting.length || b.running.length - a.running.length

const TRACK = '#343a48'
const OK = '#3fb97c'
const OK_FILL = '#2a8f5f'
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

// The color of a job's status dot says its state and nothing else; the tier has its own color.
const stateColor = (job: Job) =>
  job.stage === 'merged' || job.stage === 'committed' ? OK : job.stage === 'needs-human' || job.stage === 'waiting-input' ? WAIT : '#c9d1e0'


// A progress bar with its label inside. On surfaces that draw vector art it is a rounded SVG pill; elsewhere the
// bar is built from colored text cells (`cols` wide). `elements` is what `$.ui.resolve` returned.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const bar = (elements: any, label: string, done: number, total: number, px: number, fill: string, glyph: string, cols: number) => {
  const { Box, Text } = elements
  const Svg = 'Svg' in elements ? elements.Svg : undefined
  if (!Svg) return labeled(Box, Text, label, done, total, cols, glyph)
  return (
    <Box alignSelf="center" flexShrink={0}>
      <Svg source={pillBar({ label, done, total, width: px, fill, track: TRACK })} alt={label} width={px} height={20} />
    </Box>
  )
}

// A thin bar with no text; what it shows is written beside it. Vector art where the surface has it, text cells otherwise.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const slim = (elements: any, done: number, total: number, px: number, color: string, cols: number) => {
  const { Box, Text } = elements
  const Svg = 'Svg' in elements ? elements.Svg : undefined
  if (!Svg) return labeled(Box, Text, '', done, total, cols, color)
  return (
    <Box alignSelf="center" flexShrink={0}>
      <Svg source={slimBar({ done, total, width: px, fill: color, track: TRACK })} alt={`${done} of ${total}`} width={px} height={4} />
    </Box>
  )
}

// Centers one item on the cross axis of its row, so text sits at the middle of a bar and not on its baseline.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mid = (Box: any, node: unknown, shrink = 0) => (
  <Box alignSelf="center" flexShrink={shrink}>
    {node}
  </Box>
)

// A reviewer as a colored LED with its name beside it. The mark is a cue besides color.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const led = (Box: any, Text: any, name: string, verdict: string | undefined) => (
  <Box alignSelf="center" flexShrink={0}>
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

  on('agent.spawn', async ($, e, next) => {
    const started = await next(e)
    const jobId = jobIdFromPrompt(e.prompt)
    if (jobId && 'model' in started && started.model) {
      const model = started.model
      const role = roleOf(e.subagentType)
      await update($, observed, all => ({ ...all, [jobId]: { ...(all[jobId] ?? {}), [role]: { model } } }))
    }
    return started
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
        {mid(Box, <Text bold color={dot}>●</Text>)}
        {mid(Box, <Text bold>{lead.plan.slice(0, 20)}{more}</Text>)}
        {bar(elements, label, lead.done, lead.total, 340, OK_FILL, OK, 46)}
        {summary.waiting > 0 && mid(Box, <Text bold color={WAIT}>waiting: {waitingLabel(summary, 1)}</Text>)}
        {mid(Box, <Text dimColor>×{summary.running}</Text>)}
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
    const seen = await read($, observed)
    const onlyMine = await read($, isOnlyMine)

    // The width the pane really has, in cells; the title takes what the fixed columns leave.
    const columns = e.viewport?.columns ?? 90
    const W = { bar: 11, status: 24, time: 8 }
    const titleW = Math.max(18, columns - 8 - W.bar - W.status - W.time - 3)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cell = (width: number, node: any) => (
      <Box width={width} flexShrink={0} alignSelf="center">
        {node}
      </Box>
    )

    const header = (
      <Box flexDirection="column">
        <Box gap={1} alignItems="center">
          {cell(titleW, <Text dimColor>Task</Text>)}
          {cell(W.bar, <Text dimColor>Progress</Text>)}
          {cell(W.status, <Text dimColor>Status</Text>)}
          {cell(W.time, <Text dimColor>Time</Text>)}
        </Box>
        <Box paddingLeft={2}>
          <Text dimColor>level · in charge · reviews</Text>
        </Box>
      </Box>
    )

    // A task is two lines: what and how far, then the level, who has it and the reviews.
    const row = (r: TaskRow) => {
      const st = rowStatus(r)
      const job = r.job
      const quiet = st.kind === 'planned' || st.kind === 'landed'
      const dot = st.kind === 'landed' ? '✓' : st.kind === 'planned' ? '○' : '●'
      const color = job ? stateColor(job) : '#7d879a'
      const spent = job ? jobElapsed(job, now) : null
      const who = job ? workingNow(job, seen[job.id]) : { text: '', mismatch: false }
      const tier = job ? job.tier : r.planned?.tier ?? ''
      const owner = st.kind === 'waiting' && !who.text ? 'you' : who.text
      return (
        <Box flexDirection="column">
          <Box gap={1} alignItems="center">
            {cell(
              titleW,
              <Box gap={1}>
                <Text color={color}>{dot}</Text>
                <Text bold={st.kind === 'waiting'} dimColor={quiet} wrap="truncate-end">{r.n > 0 ? `${r.n}. ` : ''}{r.title}</Text>
              </Box>,
            )}
            {cell(W.bar, job ? slim(elements, stageStep(job), STAGE_STEPS, 70, tierColor(job.tier), 8) : <Text dimColor> </Text>)}
            {cell(W.status, <Text color={st.kind === 'waiting' ? WAIT : undefined} dimColor={quiet} wrap="truncate-end">{st.label}</Text>)}
            {cell(W.time, <Text dimColor>{spent === null ? '' : formatDuration(spent)}</Text>)}
          </Box>
          <Box gap={1} paddingLeft={2} alignItems="center">
            {tier && <Text color={tierColor(tier)}>{tier}</Text>}
            {owner && <Text color={who.mismatch ? WAIT : undefined} dimColor={!who.mismatch}>{owner}</Text>}
            {job && job.reviewers.map(rv => led(Box, Text, rv, job.reviews[rv]))}
          </Box>
        </Box>
      )
    }

    const plan = (p: PlanView) => {
      const rows = taskRows(p).filter(r => !onlyMine || rowStatus(r).kind === 'waiting')
      const elapsed = planElapsed(p, now)
      return (
        <Box flexDirection="column" borderStyle="round" borderColor={TRACK} paddingX={1}>
          <Box gap={1} alignItems="center">
            {mid(Box, <Text bold>{p.plan}</Text>)}
            {slim(elements, p.done, p.total, 140, OK, 16)}
            {mid(Box, <Text bold>{p.done}/{p.total}</Text>)}
            {mid(Box, <Text dimColor>{elapsed === null ? '' : formatDuration(elapsed)}</Text>)}
          </Box>
          {rows.length > 0 && header}
          {rows.map(row)}
          {rows.length === 0 && <Text dimColor>Nothing here needs you.</Text>}
        </Box>
      )
    }

    return (
      <Box flexDirection="column" gap={1}>
        <Box gap={2} alignItems="center">
          {mid(Box, <Text bold color={summary.waiting > 0 ? WAIT : undefined}>{situationText(summary)}</Text>)}
          <Button key="mine" label={`${onlyMine ? '[x]' : '[ ]'} only what needs me`} onPress={() => update($, isOnlyMine, () => !onlyMine)} />
        </Box>
        <Box flexDirection="column">
          <Box gap={1}>
            <Text dimColor>reviews</Text>
            {led(Box, Text, 'pass', 'PASS')}
            {led(Box, Text, 'changes', 'CHANGES')}
            {led(Box, Text, 'pending', 'pending')}
          </Box>
          <Box gap={1}>
            <Text dimColor>level</Text>
            {['light', 'medium', 'careful', 'heavy', 'fable'].map(t => (
              <Text color={tierColor(t)}>{t}</Text>
            ))}
            <Text dimColor>(easy to hard: the task's difficulty, which sets the builder's model)</Text>
          </Box>
        </Box>
        {[...summary.plans].sort(byNeed).map(plan)}
      </Box>
    )
  })
}
