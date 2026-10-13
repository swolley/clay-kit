// The contract must be self-contained, so these shapes repeat those of hooks/model.ts.
export type FactoryJob = {
  id: string
  plan: string
  task: number
  started: number | null
  updated: number | null
  repo: string
  tier: string
  stage: 'spec' | 'build' | 'waiting-input' | 'review' | 'approve' | 'merged' | 'committed' | 'needs-human'
  round: number
  reviewers: string[]
  reviews: Record<string, string>
  agents: Record<string, { model: string; effort: string }>
}

export type FactoryPlanTask = { n: number; title: string; tier: string; after: number[] }

export type FactorySummary = {
  plans: {
    plan: string
    path: string
    total: number
    done: number
    running: FactoryJob[]
    waiting: FactoryJob[]
    finished: FactoryJob[]
    planned: FactoryPlanTask[]
    tasks: FactoryPlanTask[]
  }[]
  waiting: number
  running: number
}

declare module 'claude-code' {
  interface PluginState {
    clay: {
      view: FactorySummary
      isHidden: boolean
      isOnlyMine: boolean
      observed: Record<string, Record<string, { model: string }>>
    }
  }
}
