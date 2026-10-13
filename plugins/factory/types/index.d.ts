// The contract must be self-contained, so these shapes repeat those of hooks/model.ts.
export type FactoryJob = {
  id: string
  plan: string
  repo: string
  tier: string
  stage: 'spec' | 'build' | 'waiting-input' | 'review' | 'approve' | 'merged' | 'committed' | 'needs-human'
  round: number
  reviewers: string[]
  reviews: Record<string, string>
}

export type FactorySummary = {
  plans: { plan: string; total: number; done: number; running: FactoryJob[]; waiting: FactoryJob[] }[]
  waiting: number
  running: number
}

declare module 'claude-code' {
  interface PluginState {
    factory: { view: FactorySummary; isHidden: boolean }
  }
}
