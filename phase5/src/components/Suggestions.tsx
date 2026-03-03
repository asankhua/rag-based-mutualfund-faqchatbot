import { HelpCircle } from 'lucide-react'

interface SuggestionsProps {
  suggestions: string[]
  onSuggestionClick: (suggestion: string) => void
}

export function Suggestions({ suggestions, onSuggestionClick }: SuggestionsProps) {
  return (
    <div className="suggestions-panel">
      <h4>
        <HelpCircle size={16} />
        Suggested Questions
      </h4>
      <div className="suggestions-list">
        {suggestions.map((suggestion, idx) => (
          <button
            key={idx}
            className="suggestion-item"
            onClick={() => onSuggestionClick(suggestion)}
          >
            <span className="suggestion-icon">?</span>
            <span className="suggestion-text">{suggestion}</span>
            <span className="suggestion-use">Use</span>
          </button>
        ))}
      </div>
    </div>
  )
}
