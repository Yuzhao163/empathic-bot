import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from 'recharts'
import { Send, Trash2, Plus, MessageCircle, Menu, X } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  emotion: string
  emotionProb: number
  timestamp: number
}

interface Session {
  id: string
  title: string
  messages: Message[]
  createdAt: number
}

// ============================================================================
// Emotion Config — 参考 Gradio 的情绪语义色系统
// ============================================================================

const EMOTION_CONFIG: Record<string, {
  emoji: string
  color: string
  bg: string
  label: string
  advice: string
}> = {
  positive: {
    emoji: '😊', color: '#10B981', bg: 'rgba(16,185,129,0.1)',
    label: '开心', advice: '💖 保持好心情！记录让你开心的事。'
  },
  negative: {
    emoji: '💙', color: '#3B82F6', bg: 'rgba(59,130,246,0.1)',
    label: '难过', advice: '💙 难过时，深呼吸。和信任的人聊聊会有帮助。'
  },
  anxious: {
    emoji: '🌸', color: '#8B5CF6', bg: 'rgba(139,92,246,0.1)',
    label: '焦虑', advice: '🌸 焦虑时，试着做5次深呼吸。'
  },
  angry: {
    emoji: '🤍', color: '#F59E0B', bg: 'rgba(245,158,11,0.1)',
    label: '愤怒', advice: '🤍 愤怒是正常的。描述感受，而非压抑。'
  },
  sad: {
    emoji: '😢', color: '#6366F1', bg: 'rgba(99,102,241,0.1)',
    label: '难过', advice: '😢 允许自己感受这些情绪，你值得被爱。'
  },
  neutral: {
    emoji: '🌿', color: '#6B7280', bg: 'rgba(107,114,128,0.1)',
    label: '平静', advice: '🌿 感谢分享，还有什么想聊的吗？'
  },
}

// ============================================================================
// Local Storage — 参考 n8n 的会话存储设计
// ============================================================================

const STORAGE_KEY = 'empathic_sessions'

function loadSessions(): Record<string, Session> {
  try {
    const data = localStorage.getItem(STORAGE_KEY)
    return data ? JSON.parse(data) : {}
  } catch { return {} }
}

function saveSessions(sessions: Record<string, Session>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
}

// ============================================================================
// Emotion Detection (简单版，无 Java 服务时 fallback)
// ============================================================================

function detectEmotion(text: string): { emotion: string; prob: number } {
  const t = text.toLowerCase()
  const positives = ['开心','高兴','快乐','棒','很好','谢谢','喜欢','爱','happy','great','wonderful','love','excited','joy']
  const negatives = ['难过','伤心','痛苦','抑郁','崩溃','sad','hurt','depressed','crying','misery']
  const anxious = ['焦虑','担心','害怕','紧张','不安','压力','anxious','worried','scared','nervous','stress']
  const angry = ['生气','愤怒','讨厌','烦','火','angry','hate','furious','mad']

  for (const w of positives) if (t.includes(w)) return { emotion: 'positive', prob: 0.85 }
  for (const w of negatives) if (t.includes(w)) return { emotion: 'negative', prob: 0.80 }
  for (const w of anxious) if (t.includes(w)) return { emotion: 'anxious', prob: 0.78 }
  for (const w of angry) if (t.includes(w)) return { emotion: 'angry', prob: 0.82 }
  return { emotion: 'neutral', prob: 0.70 }
}

// ============================================================================
// Emotion Trend Data
// ============================================================================

function getEmotionTrend(messages: Message[]): { index: number; value: number; emotion: string }[] {
  const userMsgs = messages.filter(m => m.role === 'user').slice(-6)
  const emotionValues: Record<string, number> = {
    positive: 100, negative: 20, anxious: 40, angry: 15, sad: 30, neutral: 60
  }
  return userMsgs.map((m, i) => ({
    index: i,
    value: emotionValues[m.emotion] ?? 60,
    emotion: m.emotion
  }))
}

// ============================================================================
// API — 参考 Gradio SSE 流式接口
// ============================================================================

const GATEWAY_URL = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8001'

async function sendMessage(sessionId: string, message: string, history: Message[]) {
  const { emotion, prob } = detectEmotion(message)

  // 保存用户消息
  const userMsg: Message = {
    id: crypto.randomUUID(),
    role: 'user',
    content: message,
    emotion,
    emotionProb: prob,
    timestamp: Date.now(),
  }

  // 构造上下文（最近6条）
  const context = history.slice(-6).map(m => ({
    role: m.role,
    content: m.content,
    emotion: m.emotion,
  }))

  // 调用后端（流式）
  const res = await fetch(`${GATEWAY_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context,
      emotion,
      emotion_prob: prob,
    }),
  })

  if (!res.ok) {
    throw new Error('Network error')
  }

  return res.json()
}

// ============================================================================
// Components
// ============================================================================

function EmotionBadge({ emotion, prob, size = 'md' }: { emotion: string; prob: number; size?: 'sm' | 'md' | 'lg' }) {
  const config = EMOTION_CONFIG[emotion] ?? EMOTION_CONFIG.neutral
  const fontSize = size === 'lg' ? '2rem' : size === 'md' ? '1.25rem' : '0.875rem'
  const padding = size === 'lg' ? '0.75rem 1.25rem' : size === 'md' ? '0.5rem 1rem' : '0.25rem 0.625rem'

  return (
    <motion.div
      className="emotion-badge"
      style={{ background: config.bg, color: config.color, padding, borderRadius: '9999px', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize }}
      animate={{ scale: [1, 1.05, 1] }}
      transition={{ duration: 0.3 }}
    >
      <span style={{ fontSize }}>{config.emoji}</span>
      <span className="emotion-label">{config.label}</span>
      <span className="emotion-prob" style={{ opacity: 0.7, fontSize: '0.75em' }}>{Math.round(prob * 100)}%</span>
    </motion.div>
  )
}

function EmotionTrendChart({ messages }: { messages: Message[] }) {
  const data = getEmotionTrend(messages)
  if (data.length < 2) return null

  return (
    <div className="emotion-trend" style={{ height: 60, marginTop: '0.5rem' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="index" hide />
          <YAxis domain={[0, 100]} hide />
          <Line type="monotone" dataKey="value" stroke="#8B5CF6" strokeWidth={2} dot={{ r: 4, fill: '#8B5CF6' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function AdviceCard({ emotion }: { emotion: string }) {
  const config = EMOTION_CONFIG[emotion] ?? EMOTION_CONFIG.neutral
  return (
    <motion.div
      className="advice-card"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        background: config.bg,
        borderLeft: `3px solid ${config.color}`,
        padding: '0.75rem 1rem',
        borderRadius: '0 0.5rem 0.5rem 0',
        fontSize: '0.875rem',
        color: config.color,
        marginTop: '0.5rem',
      }}
    >
      💡 {config.advice}
    </motion.div>
  )
}

// ============================================================================
// App
// ============================================================================

export default function App() {
  const [sessions, setSessions] = useState<Record<string, Session>>(() => loadSessions())
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const currentSession = currentSessionId ? sessions[currentSessionId] : null
  const messages = currentSession?.messages ?? []

  // 保存到 localStorage
  useEffect(() => {
    if (Object.keys(sessions).length > 0) {
      saveSessions(sessions)
    }
  }, [sessions])

  // 滚动到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 发送消息
  const handleSend = async () => {
    if (!input.trim() || streaming) return

    const text = input.trim()
    setInput('')

    // 创建新会话
    let sessionId = currentSessionId
    if (!sessionId) {
      sessionId = crypto.randomUUID()
      setCurrentSessionId(sessionId)
      setSessions(prev => ({
        ...prev,
        [sessionId!]: {
          id: sessionId!,
          title: text.slice(0, 20),
          messages: [],
          createdAt: Date.now(),
        },
      }))
    }

    const { emotion, prob } = detectEmotion(text)
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      emotion,
      emotionProb: prob,
      timestamp: Date.now(),
    }

    setSessions(prev => ({
      ...prev,
      [sessionId!]: {
        ...prev[sessionId!],
        messages: [...prev[sessionId!].messages, userMsg],
      },
    }))

    setStreaming(true)

    try {
      const result = await sendMessage(sessionId!, text, sessions[sessionId!]?.messages ?? [])

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: result.text || result.message || '我在这里，愿意听你说。',
        emotion: result.emotion || emotion,
        emotionProb: result.emotion_prob || result.emotionProb || 0.8,
        timestamp: Date.now(),
      }

      setSessions(prev => ({
        ...prev,
        [sessionId!]: {
          ...prev[sessionId!],
          messages: [...prev[sessionId!].messages, assistantMsg],
        },
      }))
    } catch {
      // Fallback
      const config = EMOTION_CONFIG[emotion]
      const fallbackMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: config?.advice || '我在这里，愿意听你说。',
        emotion: emotion,
        emotionProb: prob,
        timestamp: Date.now(),
      }
      setSessions(prev => ({
        ...prev,
        [sessionId!]: {
          ...prev[sessionId!],
          messages: [...prev[sessionId!].messages, fallbackMsg],
        },
      }))
    } finally {
      setStreaming(false)
    }
  }

  const startNewSession = () => {
    setCurrentSessionId(null)
    setSidebarOpen(false)
  }

  const switchSession = (id: string) => {
    setCurrentSessionId(id)
    setSidebarOpen(false)
  }

  const clearCurrentSession = () => {
    if (!currentSessionId) return
    const updated = { ...sessions }
    delete updated[currentSessionId]
    setSessions(updated)
    setCurrentSessionId(null)
  }

  const currentEmotion = messages.length > 0
    ? (messages[messages.length - 1].emotion || 'neutral')
    : 'neutral'

  return (
    <div className="app">
      {/* Sidebar */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            className="sidebar-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>
      <motion.aside
        className="sidebar"
        initial={{ x: -280 }}
        animate={{ x: sidebarOpen ? 0 : -280 }}
        style={{ position: 'fixed', left: 0, top: 0, bottom: 0, width: 280, zIndex: 100, background: 'white', boxShadow: '2px 0 16px rgba(0,0,0,0.1)', padding: '1.5rem', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#374151' }}>对话历史</h2>
          <button onClick={() => setSidebarOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={20} color="#6B7280" />
          </button>
        </div>

        <button
          onClick={startNewSession}
          className="new-chat-btn"
          style={{ width: '100%', padding: '0.625rem', background: '#8B5CF6', color: 'white', border: 'none', borderRadius: '0.75rem', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontWeight: 500, marginBottom: '1rem' }}
        >
          <Plus size={18} /> 新对话
        </button>

        <div className="session-list">
          {Object.values(sessions).sort((a, b) => b.createdAt - a.createdAt).map(session => (
            <button
              key={session.id}
              onClick={() => switchSession(session.id)}
              className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
              style={{
                width: '100%', padding: '0.75rem', marginBottom: '0.5rem',
                background: session.id === currentSessionId ? 'rgba(139,92,246,0.1)' : 'transparent',
                border: 'none', borderRadius: '0.5rem', cursor: 'pointer',
                textAlign: 'left' as const,
              }}
            >
              <div style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {session.title}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#9CA3AF', marginTop: '0.25rem' }}>
                {session.messages.length} 条消息
              </div>
            </button>
          ))}
        </div>
      </motion.aside>

      {/* Main */}
      <div className="main">
        {/* Header */}
        <header className="header" style={{ padding: '1rem 1.5rem', borderBottom: '1px solid #E5E7EB', display: 'flex', alignItems: 'center', gap: '1rem', background: 'white' }}>
          <button onClick={() => setSidebarOpen(true)} className="menu-btn" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}>
            <Menu size={24} color="#374151" />
          </button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1rem', fontWeight: 600, color: '#374151' }}>情感对话</h1>
            <EmotionBadge emotion={currentEmotion} prob={0.8} size="sm" />
          </div>
          {currentSessionId && (
            <button onClick={clearCurrentSession} className="clear-btn" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }} title="清空对话">
              <Trash2 size={20} color="#9CA3AF" />
            </button>
          )}
        </header>

        {/* Emotion Trend */}
        <div style={{ padding: '0.75rem 1.5rem', background: 'rgba(139,92,246,0.05)' }}>
          <div style={{ fontSize: '0.75rem', color: '#8B5CF6', fontWeight: 500, marginBottom: '0.25rem' }}>情绪趋势</div>
          <EmotionTrendChart messages={messages} />
        </div>

        {/* Messages */}
        <div className="messages" style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {messages.length === 0 && (
            <div className="empty-state" style={{ textAlign: 'center', padding: '3rem 1rem', color: '#9CA3AF' }}>
              <MessageCircle size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p style={{ fontSize: '1rem', fontWeight: 500, color: '#6B7280' }}>在这里说出你的心情</p>
              <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>我会用心倾听，温暖陪伴</p>
            </div>
          )}

          <AnimatePresence>
            {messages.map(msg => (
              <motion.div
                key={msg.id}
                className={`message ${msg.role}`}
                initial={{ opacity: 0, y: 12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                style={{
                  display: 'flex',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  alignItems: 'flex-start',
                  gap: '0.75rem',
                }}
              >
                <div className="avatar" style={{
                  width: 36, height: 36, borderRadius: '50%',
                  background: msg.role === 'user' ? '#8B5CF6' : '#10B981',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '1rem', flexShrink: 0,
                }}>
                  {msg.role === 'user' ? '😊' : '🤖'}
                </div>
                <div style={{ maxWidth: '72%' }}>
                  <div style={{
                    padding: '0.875rem 1.125rem',
                    borderRadius: msg.role === 'user' ? '1rem 1rem 0.25rem 1rem' : '1rem 1rem 1rem 0.25rem',
                    background: msg.role === 'user' ? '#8B5CF6' : 'white',
                    color: msg.role === 'user' ? 'white' : '#374151',
                    boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
                    fontSize: '0.9375rem',
                    lineHeight: 1.6,
                  }}>
                    {msg.content}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#9CA3AF', marginTop: '0.375rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {msg.role === 'assistant' && <EmotionBadge emotion={msg.emotion} prob={msg.emotionProb} size="sm" />}
                    <span>{new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                  {msg.role === 'assistant' && msg.emotion !== 'neutral' && (
                    <AdviceCard emotion={msg.emotion} />
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {streaming && (
            <motion.div
              className="message assistant"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}
            >
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#10B981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>🤖</div>
              <div style={{ padding: '0.875rem 1.125rem', background: 'white', borderRadius: '1rem 1rem 1rem 0.25rem', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
                <span className="typing-dots" style={{ display: 'inline-flex', gap: 4 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#9CA3AF', animation: 'bounce 1.2s infinite' }} />
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#9CA3AF', animation: 'bounce 1.2s 0.2s infinite' }} />
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#9CA3AF', animation: 'bounce 1.2s 0.4s infinite' }} />
                </span>
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="input-area" style={{ padding: '1rem 1.5rem', borderTop: '1px solid #E5E7EB', background: 'white' }}>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="说出你的心情..."
              rows={1}
              className="chat-input"
              style={{
                flex: 1, padding: '0.75rem 1rem', borderRadius: '1.25rem',
                border: '1.5px solid #E5E7EB', fontSize: '0.9375rem',
                resize: 'none', outline: 'none', fontFamily: 'inherit',
                lineHeight: 1.5, maxHeight: '8rem', overflowY: 'auto',
                transition: 'border-color 0.2s',
              }}
            />
            <motion.button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              whileTap={{ scale: 0.95 }}
              style={{
                width: 48, height: 48, borderRadius: '50%',
                background: input.trim() && !streaming ? '#8B5CF6' : '#E5E7EB',
                border: 'none', cursor: input.trim() && !streaming ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.2s',
              }}
            >
              <Send size={20} color="white" />
            </motion.button>
          </div>
          <p style={{ fontSize: '0.75rem', color: '#9CA3AF', textAlign: 'center', marginTop: '0.5rem' }}>
            按 Enter 发送 · Shift+Enter 换行
          </p>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }
        .app {
          display: flex;
          height: 100vh;
          background: linear-gradient(135deg, #fdf4f4 0%, #fef9f3 100%);
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        .main {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
          margin-left: 0;
        }
        @media (min-width: 768px) {
          .main { margin-left: 0; }
        }
        .chat-input:focus { border-color: #8B5CF6 !important; }
      `}</style>
    </div>
  )
}
