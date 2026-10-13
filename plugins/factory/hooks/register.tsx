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
    const more = active.length > 1 ? ` +${active.length - 1} plans` : ''
    const phases = [...new Set(lead.running.map(phaseLabel))].join(', ')
    const parts = barParts(lead.done, lead.total)
    const elapsed = planElapsed(lead, now)

    return (
      <Box>
        <Text bold>factory </Text>
        <Text color="green">{parts.filled}</Text>
        <Text dimColor>{parts.empty}</Text>
        <Text bold> {lead.done}/{lead.total} </Text>
        <Text>{percent(lead.done, lead.total)}% </Text>
        <Text dimColor>{lead.plan}{more}{elapsed === null ? '' : ` · ${formatDuration(elapsed)}`}{phases ? ` · ${phases}` : ''} </Text>
        {summary.waiting > 0 && <Text bold color="yellow">· waiting for you: {waitingLabel(summary)} </Text>}
        <Button key="hide" label="Hide" onPress={() => update($, isHidden, () => true)} />
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
      const bar = barParts(stageStep(job), STAGE_STEPS, STAGE_STEPS)
      const spent = jobElapsed(job, now)
      return (
        <Box>
          <Text bold={job.stage === 'needs-human' || job.stage === 'waiting-input'}>  {job.id} </Text>
          <Text color={tierColor(job.tier)}>{job.tier} </Text>
          <Text color={tierColor(job.tier)}>{bar.filled}</Text>
          <Text dimColor>{bar.empty} {phaseLabel(job)}{spent === null ? '' : ` · ${formatDuration(spent)}`} </Text>
          {job.reviewers.map(r => (
            <Text color={verdictColor(job.reviews[r])}>{r}:{job.reviews[r] ?? 'pending'} </Text>
          ))}
        </Box>
      )
    }

    const plan = (p: PlanView) => {
      const parts = barParts(p.done, p.total)
      const elapsed = planElapsed(p, now)
      return (
        <Box flexDirection="column">
          <Box>
            <Text bold>{p.plan} </Text>
            <Text color="green">{parts.filled}</Text>
            <Text dimColor>{parts.empty}</Text>
            <Text bold> {p.done}/{p.total} </Text>
            <Text>{percent(p.done, p.total)}%</Text>
            <Text dimColor>{elapsed === null ? '' : ` · ${formatDuration(elapsed)}`}</Text>
          </Box>
          {p.waiting.length > 0 && <Text bold color="yellow">Waiting for you · {p.waiting.length}</Text>}
          {p.waiting.map(jobLine)}
          {p.running.length > 0 && <Text bold>Running · {p.running.length}</Text>}
          {p.running.map(jobLine)}
          {p.finished.length > 0 && (
            <Button key={`fin-${p.plan}`} label={`${isOpen ? '▾' : '▸'} Finished · ${p.finished.length}`} onPress={() => update($, isFinishedOpen, () => !isOpen)} />
          )}
          {isOpen && p.finished.map(jobLine)}
          {p.planned.length > 0 && <Text bold>Planned · {p.planned.length}</Text>}
          {p.planned.map(t => (
            <Box>
              <Text dimColor>  {t.n}. {t.title} </Text>
              <Text color={tierColor(t.tier)}>{t.tier}</Text>
              <Text dimColor>{t.after.length > 0 ? ` · after ${t.after.join(', ')}` : ''}</Text>
            </Box>
          ))}
        </Box>
      )
    }

    return (
      <Box flexDirection="column" gap={1}>
        {[...summary.plans].sort(byNeed).map(plan)}
      </Box>
    )
  })
}
