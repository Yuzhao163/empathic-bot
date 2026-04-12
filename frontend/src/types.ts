export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  emotion: string
  emotionProb: number
  timestamp: number
}

export interface Session {
  id: string
  title: string
  messages: Message[]
  createdAt: number
}

export interface ChatResult {
  text?: string
  message?: string
  emotion: string
  emotion_prob?: number
  emotionProb?: number
  advice?: string
}

export type ThemeMode = 'light' | 'dark' | 'auto'

export interface EmotionConfig {
  emoji: string
  color: string
  bg: string
  label: string
  advice: string
}

// Light theme
export const LIGHT_THEME = {
  bg: 'linear-gradient(135deg, #fdf4f4 0%, #fef9f3 100%)',
  surface: '#ffffff',
  text: '#374151',
  textMuted: '#9CA3AF',
  border: '#E5E7EB',
  sidebar: '#ffffff',
  headerBg: '#ffffff',
  inputBg: '#ffffff',
  accent: '#8B5CF6',
  userBubble: '#8B5CF6',
  assistantBubble: '#ffffff',
  userText: '#ffffff',
  assistantText: '#374151',
  trendBg: 'rgba(139,92,246,0.05)',
  trendColor: '#8B5CF6',
  overlay: 'rgba(0,0,0,0.3)',
  errorBg: 'rgba(239,68,68,0.1)',
  errorColor: '#DC2626',
}

// Dark theme
export const DARK_THEME = {
  bg: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
  surface: '#1e1e2e',
  text: '#E5E7EB',
  textMuted: '#6B7280',
  border: '#374151',
  sidebar: '#1e1e2e',
  headerBg: '#1e1e2e',
  inputBg: '#2d2d3d',
  accent: '#A78BFA',
  userBubble: '#7C3AED',
  assistantBubble: '#2d2d3d',
  userText: '#ffffff',
  assistantText: '#E5E7EB',
  trendBg: 'rgba(139,92,246,0.15)',
  trendColor: '#A78BFA',
  overlay: 'rgba(0,0,0,0.6)',
  errorBg: 'rgba(239,68,68,0.2)',
  errorColor: '#F87171',
}

export type Theme = typeof LIGHT_THEME

export const EMOTION_CONFIG: Record<string, EmotionConfig> = {
  positive: { emoji: '😊', color: '#10B981', bg: 'rgba(16,185,129,0.15)', label: '开心', advice: '💖 保持好心情！' },
  negative: { emoji: '💙', color: '#3B82F6', bg: 'rgba(59,130,246,0.15)', label: '难过', advice: '💙 深呼吸，和信任的人聊聊。' },
  anxious:  { emoji: '🌸', color: '#8B5CF6', bg: 'rgba(139,92,246,0.15)', label: '焦虑', advice: '🌸 做5次深呼吸，专注当下。' },
  angry:    { emoji: '🤍', color: '#F59E0B', bg: 'rgba(245,158,11,0.15)', label: '愤怒', advice: '🤍 描述感受，而非压抑。' },
  sad:      { emoji: '😢', color: '#6366F1', bg: 'rgba(99,102,241,0.15)', label: '难过', advice: '😢 允许自己感受这些情绪。' },
  neutral:  { emoji: '🌿', color: '#6B7280', bg: 'rgba(107,114,128,0.15)', label: '平静', advice: '🌿 继续说吧。' },
}
