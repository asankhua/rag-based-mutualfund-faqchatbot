import { Send } from 'lucide-react'

interface ChatInputProps {
  input: string
  setInput: (value: string) => void
  onSend: () => void
  isLoading: boolean
}

export function ChatInput({ input, setInput, onSend, isLoading }: ChatInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="chat-input-container">
      <div className="chat-input-wrapper">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about HDFC mutual funds..."
          disabled={isLoading}
          className="chat-input"
        />
        <button
          onClick={onSend}
          disabled={!input.trim() || isLoading}
          className="send-button"
        >
          <Send size={20} />
        </button>
      </div>
      <p className="input-hint">Press Enter to send</p>
    </div>
  )
}
