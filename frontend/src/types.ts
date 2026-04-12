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

export interface EmotionConfig {
  emoji: string
  color: string
  bg: string
  label: string
  advice: string
}

export const EMOTION_CONFIG: Record<string, EmotionConfig> = {
  positive: { emoji: '😊', color: '#10B981', bg: 'rgba(16,185,129,0.1)', label: '开心', advice: '💖 保持好心情！' },
  negative: { emoji: '💙', color: '#3B82F6', bg: 'rgba(59,130,246,0.1)', label: '难过', advice: '💙 深呼吸，和信任的人聊聊。' },
  anxious:  { emoji: '🌸', color: '#8B5CF6', bg: 'rgba(139,92,246,0.1)', label: '焦虑', advice: '🌸 做5次深呼吸，专注当下。' },
  angry:    { emoji: '🤍', color: '#F59E0B', bg: 'rgba(245,158,11,0.1)', label: '愤怒', advice: '🤍 描述感受，而非压抑。' },
  sad:      { emoji: '😢', color: '#6366F1', bg: 'rgba(99,102,241,0.1)', label: '难过', advice: '😢 允许自己感受这些情绪。' },
  neutral:  { emoji: '🌿', color: '#6B7280', bg: 'rgba(107,114,128,0.1)', label: '平静', advice: '🌿 继续说吧。' },
}
