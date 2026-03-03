import { useState, useRef, useEffect } from 'react'
import './App.css'
import { Sidebar } from './components/Sidebar'
import { ChatArea } from './components/ChatArea'
import { SourcesPanel } from './components/SourcesPanel'
import { ChatInput } from './components/ChatInput'
import { Disclaimer } from './components/Disclaimer'
import type { Message, Fund } from './types'
import { sendChatQuery, fetchFunds } from './api'

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello! I\'m your Mutual Fund FAQ Assistant. I can help you with factual information about HDFC mutual funds on INDMoney. What would you like to know?',
      sources: [],
      timestamp: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [funds, setFunds] = useState<Fund[]>([])
  const [selectedFund, setSelectedFund] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch funds on mount
  useEffect(() => {
    fetchFunds().then(setFunds).catch(console.error)
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      sources: [],
      timestamp: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await sendChatQuery(input)
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        metadata: response.metadata,
        timestamp: new Date().toISOString(),
        isRefusal: response.metadata?.is_refusal,
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        sources: [],
        timestamp: new Date().toISOString(),
        isError: true,
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleFundSelect = (fundId: string) => {
    setSelectedFund(fundId)
    const fund = funds.find((f) => f.scheme_id === fundId)
    if (fund) {
      setInput(`Tell me about ${fund.name}`)
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
  }

  // Get sources from the last assistant message
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === 'assistant')
  const currentSources = lastAssistantMessage?.sources || []

  return (
    <div className="app">
      <Sidebar
        funds={funds}
        selectedFund={selectedFund}
        onFundSelect={handleFundSelect}
      />
      
      <main className="main-content">
        <header className="chat-header">
          <div className="header-info">
            <div className="assistant-avatar">MF</div>
            <div className="header-text">
              <h1>Mutual Fund Assistant</h1>
              <p>Factual information about HDFC mutual funds</p>
            </div>
          </div>
        </header>

        <Disclaimer />

        <ChatArea
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
          onSuggestionClick={handleSuggestionClick}
        />

        <ChatInput
          input={input}
          setInput={setInput}
          onSend={handleSend}
          isLoading={isLoading}
        />
      </main>

      <SourcesPanel sources={currentSources} />
    </div>
  )
}

export default App
