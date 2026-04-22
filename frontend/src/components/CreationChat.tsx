import { useState, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import type { Keyword, ChatMessage as ChatMessageType, WorkflowSSEEvent } from '@/types'
import ChatInput from './ChatInput'
import ChatMessage from './ChatMessage'
import { useSSE } from '@/hooks/useSSE'
import { startGeneration } from '@/lib/api'

interface Props {
  tags: Keyword[]
  onRemoveTag: (text: string) => void
  onPreviewArticle: (articleId: string) => void
  onArticleGenerated: () => void
}

let msgCounter = 0

export default function CreationChat({ tags, onRemoveTag, onPreviewArticle, onArticleGenerated }: Props) {
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages])

  const addMessage = useCallback((msg: Omit<ChatMessageType, 'id' | 'timestamp'>) => {
    setMessages(prev => [...prev, { ...msg, id: `msg-${++msgCounter}`, timestamp: Date.now() }])
  }, [])

  const handleSSEEvent = useCallback((e: WorkflowSSEEvent) => {
    const d = e.data
    switch (e.event) {
      case 'phase_start':
        addMessage({
          role: 'agent',
          content: String(d.message ?? ''),
          meta: {
            type: 'phase_start',
            phase: Number(d.phase),
            totalPhases: Number(d.total),
            agent: String(d.agent ?? ''),
          },
        })
        break
      case 'agent_response':
        addMessage({
          role: 'agent',
          content: `${d.agent} 完成撰写 (${d.char_count} 字)`,
          meta: {
            type: 'agent_response',
            agent: String(d.agent ?? ''),
            round: Number(d.round ?? 0),
          },
        })
        break
      case 'judge_decision':
        addMessage({
          role: 'agent',
          content: '',
          meta: {
            type: 'judge_decision',
            decision: String(d.decision ?? ''),
            score: Number(d.score ?? 0),
            round: Number(d.round ?? 0),
          },
        })
        break
      case 'workflow_end':
        addMessage({
          role: 'result',
          content: '文章生成完成',
          meta: {
            type: 'result',
            articleId: String(d.article_id ?? d.output_path ?? ''),
            title: String(d.title ?? '公众号文章'),
            score: Number(d.score ?? d.final_score ?? 0),
            rounds: Number(d.rounds ?? 0),
            outputPath: String(d.output_path ?? ''),
          },
        })
        break
      case 'progress':
      case 'warning':
      case 'error':
        addMessage({
          role: 'agent',
          content: String(d.message ?? JSON.stringify(d)),
          meta: { type: e.event as 'progress' | 'warning' | 'error' },
        })
        break
    }
  }, [addMessage])

  const handleDone = useCallback(() => {
    setIsGenerating(false)
    onArticleGenerated()
  }, [onArticleGenerated])

  const { connect } = useSSE(handleSSEEvent, handleDone)

  const handleSend = async (message: string) => {
    addMessage({ role: 'user', content: message })
    setIsGenerating(true)

    try {
      const { task_id } = await startGeneration(message)
      addMessage({
        role: 'agent',
        content: '多智能体工作流已启动，正在为你创作...',
        meta: { type: 'progress' },
      })
      connect(task_id)
    } catch {
      addMessage({
        role: 'agent',
        content: '连接后端失败。请确保 Flask 后端已启动 (python scripts/web_app.py --port 5000)',
        meta: { type: 'error' },
      })
      setIsGenerating(false)
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto flex flex-col" style={{ height: '500px' }}>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
        style={{
          background: 'var(--color-bg-surface)',
          borderRadius: '1rem 1rem 0 0',
          border: '1px solid var(--color-border)',
          borderBottom: 'none',
        }}
      >
        {messages.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="h-full flex flex-col items-center justify-center text-center"
          >
            <div className="w-16 h-16 rounded-2xl mb-4 flex items-center justify-center"
                 style={{
                   background: 'linear-gradient(135deg, var(--color-accent-indigo)20, var(--color-accent-pink)20)',
                   border: '1px solid var(--color-border)',
                 }}>
              <span className="text-2xl">✦</span>
            </div>
            <h3 className="text-sm font-medium mb-1" style={{ color: 'var(--color-text-primary)' }}>
              开始你的创作
            </h3>
            <p className="text-xs max-w-xs" style={{ color: 'var(--color-text-muted)' }}>
              从词云中选择灵感关键词，或直接在下方输入你的创意
            </p>
          </motion.div>
        )}
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} onPreview={onPreviewArticle} />
        ))}
      </div>

      <div style={{
        background: 'var(--color-bg-surface)',
        borderRadius: '0 0 1rem 1rem',
        border: '1px solid var(--color-border)',
        borderTop: '1px solid var(--color-border)',
        padding: '0.75rem',
      }}>
        <ChatInput
          tags={tags}
          onRemoveTag={onRemoveTag}
          onSend={handleSend}
          disabled={isGenerating}
        />
      </div>
    </div>
  )
}
