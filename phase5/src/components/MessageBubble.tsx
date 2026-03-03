import type { Message } from '../types'
import { Info, AlertCircle } from 'lucide-react'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  
  return (
    <div className={`message ${isUser ? 'user-message' : 'assistant-message'}`}>
      {!isUser && (
        <div className={`message-avatar ${message.isRefusal ? 'refusal-avatar' : ''}`}>
          {message.isRefusal ? <Info size={16} /> : message.isError ? <AlertCircle size={16} /> : 'MF'}
        </div>
      )}
      
      <div className={`message-content ${message.isRefusal ? 'refusal-content' : ''} ${message.isError ? 'error-content' : ''}`}>
        <div className="message-text">{message.content}</div>
        
        {!isUser && message.sources.length > 0 && (
          <div className="message-sources">
            <strong>Sources:</strong>
            <ul>
              {message.sources.map((source, idx) => (
                <li key={idx}>
                  <a href={source} target="_blank" rel="noopener noreferrer">
                    {source}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
        
        <span className="message-time">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}
