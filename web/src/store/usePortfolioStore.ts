import { create } from 'zustand'

export interface HoldingDetail {
  holding: {
    symbol: string
    name: string
    market: string
    tags: string[]
    data_status: string
    created_at: string
  }
  position?: {
    symbol: string
    quantity: number
    avg_cost: number
    current_price?: number
    market_value?: number
    unrealized_pnl?: number
    unrealized_pnl_pct?: number
    updated_at: string
  }
}

interface PortfolioState {
  holdings: HoldingDetail[]
  selectedSymbol: string
  setHoldings: (holdings: HoldingDetail[]) => void
  setSelectedSymbol: (symbol: string) => void
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  holdings: [],
  selectedSymbol: '',
  setHoldings: (holdings) => set({ holdings }),
  setSelectedSymbol: (selectedSymbol) => set({ selectedSymbol }),
}))
