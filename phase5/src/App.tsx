import { useState, useRef, useEffect } from 'react'
import './App.css'
import { Sidebar } from './components/Sidebar.tsx'
import { ChatArea } from './components/ChatArea.tsx'
import { SourcesPanel } from './components/SourcesPanel.tsx'
import { ChatInput } from './components/ChatInput.tsx'
import { Disclaimer } from './components/Disclaimer.tsx'
import type { Message, Fund, SystemStatus } from './types.ts'
import { sendChatQuery, fetchFunds, fetchStatus } from './api.ts'

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
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [isLoadingData, setIsLoadingData] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  // Fetch funds and system status on mount
  useEffect(() => {
    const loadData = async () => {
      setIsLoadingData(true)
      setError(null)
      
      try {
        const fundsData = await fetchFunds()
        setFunds(fundsData)
      } catch (err) {
        console.error('Failed to fetch funds:', err)
        setError('Failed to connect to backend API. Please check your connection.')
        setFunds([])
      }
      
      try {
        const statusData = await fetchStatus()
        setSystemStatus(statusData)
      } catch (err) {
        console.error('Failed to fetch status:', err)
      }
      
      setIsLoadingData(false)
    }
    
    loadData()
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
    } catch (error: any) {
      console.error('Chat error:', error)
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${error.message || 'Failed to connect to backend API. Please check if the backend is running.'}`,
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

  if (isLoadingData) {
    return (
      <div className="app" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#1a1d29', color: 'white' }}>
        <div>Loading...</div>
      </div>
    )
  }

  return (
    <div className="app">
      {error && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, background: '#ef4444', color: 'white', padding: '12px', textAlign: 'center', zIndex: 1000 }}>
          {error}
        </div>
      )}
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
          {(systemStatus?.last_scheduler_run || systemStatus?.last_updated) && (
            <div className="last-updated">
              <span className={`freshness-indicator ${systemStatus.data_freshness}`}></span>
              <span className="update-text">
                Last updated: {new Date(systemStatus.last_scheduler_run || systemStatus.last_updated!).toLocaleDateString('en-IN', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </span>
            </div>
          )}
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
