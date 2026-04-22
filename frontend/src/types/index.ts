export interface Keyword {
  text: string
  category: KeywordCategory
  weight?: number
}

export type KeywordCategory = 'emotions' | 'objects' | 'trending' | 'styles' | 'memes'

export const CATEGORY_COLORS: Record<KeywordCategory, string> = {
  emotions: '#f97316',
  objects:  '#06b6d4',
  trending: '#3b82f6',
  styles:   '#a855f7',
  memes:    '#ec4899',
}

export const CATEGORY_LABELS: Record<KeywordCategory, string> = {
  emotions: '情绪',
  objects:  '事物',
  trending: '时事',
  styles:   '风格',
  memes:    '梗',
}

export interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'result'
  content: string
  timestamp: number
  meta?: AgentProgressMeta | ArticleResultMeta
}

export interface AgentProgressMeta {
  type: 'phase_start' | 'agent_response' | 'judge_decision' | 'progress' | 'warning' | 'error'
  phase?: number
  totalPhases?: number
  agent?: string
  decision?: string
  score?: number
  round?: number
}

export interface ArticleResultMeta {
  type: 'result'
  articleId: string
  title: string
  score: number
  rounds: number
  outputPath: string
}

export interface Article {
  id: string
  title: string
  createdAt: string
  score: number
  rounds: number
  format: string
  previewUrl: string
  downloadUrl: string
}

export interface WorkflowSSEEvent {
  event: string
  data: Record<string, unknown>
}

export type ThemeMode = 'dark' | 'light'
