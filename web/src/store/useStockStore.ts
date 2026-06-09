import { create } from 'zustand'

export interface KlineRecord {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Quote {
  symbol: string
  name?: string
  price: number
  open: number
  high: number
  low: number
  prev_close: number
  volume: number
  turnover: number
  change_pct: number
}

export interface Fundamentals {
  symbol: string
  name?: string
  pe_ttm?: number
  pb?: number
  roe?: number
  revenue_growth?: number
  profit_growth?: number
  debt_ratio?: number
  [key: string]: unknown
}

export interface NewsItem {
  title: string
  content?: string
  source?: string
  published_at?: string
  url?: string
  relevance_score?: number
  institution?: string
  rating?: string
  target_price?: string
  predict_this_year_eps?: string
  predict_next_year_eps?: string
}

interface StockState {
  quote: Quote | null
  kline: KlineRecord[]
  fundamentals: Fundamentals | null
  indicators: Record<string, unknown> | null
  news: NewsItem[]
  announcements: NewsItem[]
  researchReports: NewsItem[]
  setQuote: (quote: Quote | null) => void
  setKline: (kline: KlineRecord[]) => void
  setFundamentals: (f: Fundamentals | null) => void
  setIndicators: (i: Record<string, unknown> | null) => void
  setNews: (news: NewsItem[]) => void
  setAnnouncements: (items: NewsItem[]) => void
  setResearchReports: (items: NewsItem[]) => void
  reset: () => void
}

export const useStockStore = create<StockState>((set) => ({
  quote: null,
  kline: [],
  fundamentals: null,
  indicators: null,
  news: [],
  announcements: [],
  researchReports: [],
  setQuote: (quote) => set({ quote }),
  setKline: (kline) => set({ kline }),
  setFundamentals: (fundamentals) => set({ fundamentals }),
  setIndicators: (indicators) => set({ indicators }),
  setNews: (news) => set({ news }),
  setAnnouncements: (announcements) => set({ announcements }),
  setResearchReports: (researchReports) => set({ researchReports }),
  reset: () => set({
    quote: null, kline: [], fundamentals: null, indicators: null,
    news: [], announcements: [], researchReports: [],
  }),
}))
