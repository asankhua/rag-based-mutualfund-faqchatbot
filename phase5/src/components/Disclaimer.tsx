import { AlertTriangle, Info } from 'lucide-react'

export function Disclaimer() {
  return (
    <div className="disclaimer-container">
      <div className="disclaimer-banner">
        <Info size={16} />
        <p>
          This chatbot is a <strong>facts-only FAQ assistant</strong> for certain HDFC mutual fund schemes on INDMoney. 
          It does not provide investment advice or handle personal/account-specific queries.
        </p>
      </div>
      
      <div className="disclaimer-footer">
        <AlertTriangle size={14} />
        <p>Past performance is not indicative of future returns. Please read all scheme-related documents carefully before investing.</p>
      </div>
    </div>
  )
}
