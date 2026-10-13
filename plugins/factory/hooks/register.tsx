import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import { bar, phaseLabel, scan, summarize, waitingIds } from './model'
import type { Fs, Job, PlanView, Summary } from './model'

const PANE = 'factory-agents'
const POLL_MS = 3000

const view = atom({ plugin: 'factory', key: 'view' } as const, { plans: [], waiting: 0, running: 0 } as Summary)
const isHidden = atom({ plugin: 'factory', key: 'isHidden' } as const, false)

const verdictColor = (verdict: string | undefined) => (verdict === 'PASS' ? 'green' : verdict === 'CHANGES' ? 'red' : undefined)

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
    const lead = summary.plans.find(p => p.running.length + p.waiting.length > 0) ?? summary.plans[0]
    if (!lead) return next(e)
    const more = summary.plans.length > 1 ? ` +${summary.plans.length - 1} plans` : ''
    const phases = [...new Set(lead.running.map(phaseLabel))].join(', ')

    return (
      <Box>
        <Text bold>factory </Text>
        <Text>{bar(lead.done, lead.total)} {lead.done}/{lead.total} </Text>
        <Text dimColor>{lead.plan}{more}{phases ? ` · ${phases}` : ''} </Text>
        {summary.waiting > 0 && <Text bold color="yellow">· {summary.waiting} waiting for you </Text>}
        <Button key="hide" label="Hide" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const summary = await read($, view)
    if (summary.plans.length === 0) return <Text dimColor>No factory jobs found here.</Text>

    const line = (job: Job) => (
      <Box>
        <Text bold={job.stage === 'needs-human' || job.stage === 'waiting-input'}>{job.id} </Text>
        <Text dimColor>{job.tier} · {phaseLabel(job)} </Text>
        {job.reviewers.map(r => (
          <Text color={verdictColor(job.reviews[r])}>{r}:{job.reviews[r] ?? 'pending'} </Text>
        ))}
      </Box>
    )

    return (
      <Box flexDirection="column">
        {summary.plans.map((p: PlanView) => (
          <Box flexDirection="column">
            <Text bold>{p.plan} {bar(p.done, p.total)} {p.done}/{p.total}</Text>
            {[...p.waiting, ...p.running].map(line)}
          </Box>
        ))}
      </Box>
    )
  })
}
