export interface LivePortfolioConfig {
  inception_date: string
  initialized_at: string
}

export interface LivePosition {
  code: string
  name: string
  units: number
  position_pct: number
  opened_date: string
  last_action_date: string
  updated_at: string
}

export type LivePlanStatus = 'pending' | 'confirmed' | 'skipped'
export type LivePlanKind = 'BUY' | 'TOPUP' | 'REDUCE' | 'SELL'

export interface LiveTradePlan {
  id: number
  signal_date: string
  execution_date: string
  code: string
  name: string
  kind: LivePlanKind
  target_units: number
  target_position_pct: number
  reason: string
  status: LivePlanStatus
  created_at: string
  resolved_at: string | null
}

export interface LivePortfolioState {
  config: LivePortfolioConfig | null
  positions: LivePosition[]
  total_position_pct: number
  pending_plans: LiveTradePlan[]
  history: LiveTradePlan[]
}
