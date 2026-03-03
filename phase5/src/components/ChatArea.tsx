import type { Message } from '../types'
import { MessageBubble } from './MessageBubble'
import { Suggestions } from './Suggestions'
import { Loader2 } from 'lucide-react'

interface ChatAreaProps {
  messages: Message[]
  isLoading: boolean
  messagesEndRef: React.RefObject<HTMLDivElement | null>
  onSuggestionClick: (suggestion: string) => void
}

const SUGGESTIONS = [
  'What is the NAV of HDFC Flexi Cap Fund?',
  'What is the expense ratio of HDFC Small Cap Fund?',
  'What is exit load?',
  'Tell me about the risk profile',
  'What is the minimum investment amount?',
]

export function ChatArea({ messages, isLoading, messagesEndRef, onSuggestionClick }: ChatAreaProps) {
  const showSuggestions = messages.length === 1 // Only show if just welcome message

  return (
    <div className="chat-area">
      <div className="messages-container">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        
        {isLoading && (
          <div className="message assistant-message loading-message">
            <div className="message-avatar">MF</div>
            <div className="message-content">
              <Loader2 className="spinner" size={20} />
              <span>Thinking...</span>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {showSuggestions && (
        <Suggestions suggestions={SUGGESTIONS} onSuggestionClick={onSuggestionClick} />
      )}
    </div>
  )
}
