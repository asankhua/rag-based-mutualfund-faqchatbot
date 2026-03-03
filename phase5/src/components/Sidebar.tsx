import type { Fund } from '../types.ts'
import { Wallet, ChevronRight } from 'lucide-react'

interface SidebarProps {
  funds: Fund[]
  selectedFund: string | null
  onFundSelect: (fundId: string) => void
}

export function Sidebar({ funds, selectedFund, onFundSelect }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <Wallet size={24} />
          <span>MF Chatbot</span>
        </div>
      </div>

      <div className="sidebar-section">
        <h3>Available Funds</h3>
        <p className="sidebar-subtitle">Click to ask about a fund</p>
        
        <div className="fund-list">
          {funds.map((fund) => (
            <button
              key={fund.scheme_id}
              className={`fund-item ${selectedFund === fund.scheme_id ? 'active' : ''}`}
              onClick={() => onFundSelect(fund.scheme_id)}
            >
              <div className="fund-icon">
                {fund.name.charAt(0)}
              </div>
              <div className="fund-info">
                <span className="fund-name">{fund.name}</span>
                <span className="fund-risk">{fund.overview.risk}</span>
              </div>
              <ChevronRight size={16} className="fund-arrow" />
            </button>
          ))}
        </div>
      </div>

      <div className="sidebar-footer">
        <p>8 HDFC Mutual Funds</p>
      </div>
    </aside>
  )
}
