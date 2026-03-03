export interface FundOverview {
  nav?: string
  returns_since_inception?: string
  returns_1y?: string | null
  returns_3y?: string | null
  returns_5y?: string | null
  expense_ratio?: string
  benchmark?: string
  aum?: string
  inception_date?: string
  min_lumpsum?: string
  min_sip?: string
  exit_load?: string
  lock_in?: string
  turnover?: string
  risk?: string
}

export interface Fund {
  scheme_id: string
  name: string
  source_url: string
  overview: FundOverview
  last_scraped_at?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: string[]
  timestamp: string
  metadata?: {
    intent?: string
    is_refusal?: boolean
    chunks_retrieved?: number
    mentioned_schemes?: string[]
  }
  isRefusal?: boolean
  isError?: boolean
}

export interface ChatQueryRequest {
  message: string
  session_id?: string
  user_id?: string
}

export interface ChatQueryResponse {
  answer: string
  sources: string[]
  metadata?: {
    intent?: string
    is_refusal?: boolean
    chunks_retrieved?: number
    mentioned_schemes?: string[]
  }
}

export interface FundListResponse {
  funds: Fund[]
  total: number
}
