import { motion } from 'framer-motion'
import type { ChatMessage as ChatMessageType } from '@/types'
import AgentProgress from './AgentProgress'
import ResultCard from './ResultCard'

interface Props {
  message: ChatMessageType
  onPreview?: (articleId: string) => void
}

export default function ChatMessage({ message, onPreview }: Props) {
  if (message.role === 'user') {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div
          className="max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm"
          style={{
            background: 'linear-gradient(135deg, var(--color-accent-indigo), var(--color-accent-violet))',
            color: 'white',
          }}
        >
          {message.content}
        </div>
      </motion.div>
    )
  }

  if (message.role === 'result' && message.meta && 'articleId' in message.meta) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ResultCard meta={message.meta} onPreview={onPreview} />
      </motion.div>
    )
  }

  // Agent message
  const meta = message.meta
  if (meta && 'agent' in meta) {
    const isScore = meta.type === 'judge_decision'
    if (isScore) {
      return (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 py-1 pl-11 text-sm"
        >
          <span style={{ color: 'var(--color-accent-green)' }}>
            {meta.decision === 'PASS' ? '✅' : meta.decision === 'REVISE' ? '🔄' : '✨'} {meta.decision}
          </span>
          {meta.score != null && (
            <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: meta.score >= 7.5 ? '#10b98120' : meta.score >= 7 ? '#f9731620' : '#ef444420',
                    color: meta.score >= 7.5 ? '#10b981' : meta.score >= 7 ? '#f97316' : '#ef4444',
                  }}>
              {meta.score.toFixed(1)}
            </span>
          )}
          {meta.round != null && (
            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              Round {meta.round}
            </span>
          )}
        </motion.div>
      )
    }

    return (
      <AgentProgress
        agent={meta.agent}
        phase={meta.phase}
        totalPhases={meta.totalPhases}
        message={message.content}
        isActive={meta.type === 'phase_start'}
      />
    )
  }

  // Generic agent message
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex justify-start"
    >
      <div
        className="max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm"
        style={{
          background: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-secondary)',
        }}
      >
        {message.content}
      </div>
    </motion.div>
  )
}
