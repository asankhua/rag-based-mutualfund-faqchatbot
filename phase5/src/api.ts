import type { ChatQueryRequest, ChatQueryResponse, FundListResponse, SystemStatus } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://rag-based-mutualfund-faqchatbot.onrender.com'

export async function sendChatQuery(message: string): Promise<ChatQueryResponse> {
  const request: ChatQueryRequest = { message }
  
  try {
    const response = await fetch(`${API_BASE_URL}/chat/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('API Error:', response.status, errorText)
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    return response.json()
  } catch (error) {
    console.error('Fetch Error:', error)
    throw error
  }
}

export async function fetchFunds(): Promise<FundListResponse['funds']> {
  const response = await fetch(`${API_BASE_URL}/funds`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch funds')
  }

  const data: FundListResponse = await response.json()
  return data.funds
}

export async function fetchFund(schemeId: string) {
  const response = await fetch(`${API_BASE_URL}/funds/${schemeId}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch fund')
  }

  return response.json()
}

export async function fetchStatus(): Promise<SystemStatus> {
  const response = await fetch(`${API_BASE_URL}/status`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch status')
  }

  return response.json()
}
