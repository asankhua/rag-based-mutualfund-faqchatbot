import type { ChatQueryRequest, ChatQueryResponse, FundListResponse } from './types'

const API_BASE_URL = 'http://localhost:8000'

export async function sendChatQuery(message: string): Promise<ChatQueryResponse> {
  const request: ChatQueryRequest = { message }
  
  const response = await fetch(`${API_BASE_URL}/chat/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to send message')
  }

  return response.json()
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
