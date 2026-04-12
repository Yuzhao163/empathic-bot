/**
 * API Client — 统一封装，支持 SSE 流式
 */

import type { ChatResult } from './types'

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || ''

function checkUrl() {
  if (!GATEWAY_URL) {
    console.error('[EmpathicBot] VITE_GATEWAY_URL is not set. See .env.example.')
  }
}

export async function apiChat(
  sessionId: string,
  message: string,
  history: import('./types').Message[]
): Promise<ChatResult> {
  checkUrl()
  if (!GATEWAY_URL) throw new Error('VITE_GATEWAY_URL not configured')

  const res = await fetch(`${GATEWAY_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context: history.slice(-6), emotion: '', emotion_prob: 0.5 }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(err.error || `HTTP ${res.status}`)
  }

  return res.json()
}

/**
 * SSE 流式聊天 — 增量渲染
 * onToken: 每收到一个 token 就回调
 * onDone: 流结束时回调（带最终 emotion/advice）
 * onError: 出错时回调
 */
export async function apiChatStream(
  sessionId: string,
  message: string,
  emotion: string,
  emotionProb: number,
  history: import('./types').Message[],
  onToken: (token: string) => void,
  onDone: (result: { emotion: string; advice?: string }) => void,
  onError: (err: Error) => void
) {
  checkUrl()
  if (!GATEWAY_URL) {
    onError(new Error('VITE_GATEWAY_URL not configured'))
    return
  }

  try {
    const res = await fetch(`${GATEWAY_URL}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, context: history.slice(-6), emotion, emotion_prob: emotionProb }),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
      throw new Error(err.error || `HTTP ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('ReadableStream not supported')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // keep incomplete line in buffer

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (!data) continue

        try {
          const parsed = JSON.parse(data)
          if (parsed.done) {
            onDone({ emotion: parsed.emotion || emotion, advice: parsed.advice })
          } else if (parsed.token) {
            onToken(parsed.token)
          }
        } catch {
          // skip malformed JSON (e.g. partial chunk)
        }
      }
    }
  } catch (e) {
    onError(e instanceof Error ? e : new Error(String(e)))
  }
}

export async function apiHealth(): Promise<{ healthy: boolean; python: boolean; redis: boolean }> {
  checkUrl()
  if (!GATEWAY_URL) return { healthy: false, python: false, redis: false }
  try {
    const res = await fetch(`${GATEWAY_URL}/health`)
    if (!res.ok) return { healthy: false, python: false, redis: false }
    return res.json()
  } catch {
    return { healthy: false, python: false, redis: false }
  }
}
