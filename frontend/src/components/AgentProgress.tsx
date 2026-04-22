import { motion } from 'framer-motion'

const AGENT_CONFIG: Record<string, { icon: string; label: string; color: string }> = {
  'news-researcher':   { icon: '🔍', label: '时事研究员', color: '#3b82f6' },
  'deep-thinker':      { icon: '🧠', label: '深度思考者', color: '#8b5cf6' },
  'meme-master':       { icon: '🎭', label: 'Meme大师',   color: '#ec4899' },
  'chief-editor':      { icon: '✏️', label: '铁面主编',   color: '#f97316' },
  'central-judge':     { icon: '⚖️', label: '中控裁判',   color: '#10b981' },
  'article-renderer':  { icon: '🎨', label: '文章渲染器', color: '#06b6d4' },
}

interface Props {
  agent?: string
  phase?: number
  totalPhases?: number
  message?: string
  isActive?: boolean
}

export default function AgentProgress({ agent, phase, totalPhases, message, isActive }: Props) {
  const config = agent ? AGENT_CONFIG[agent] : null

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className="flex items-start gap-3 py-2"
    >
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-base"
        style={{
          background: config ? `${config.color}20` : 'var(--color-bg-elevated)',
          border: `1px solid ${config?.color ?? 'var(--color-border)'}40`,
        }}
      >
        {config?.icon ?? '✦'}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          {phase != null && totalPhases != null && (
            <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--color-bg-elevated)', color: 'var(--color-text-secondary)' }}>
              {phase}/{totalPhases}
            </span>
          )}
          <span className="font-medium" style={{ color: config?.color ?? 'var(--color-text-primary)' }}>
            {config?.label ?? agent ?? '系统'}
          </span>
          {isActive && (
            <span className="flex gap-0.5">
              {[0, 1, 2].map(i => (
                <motion.span
                  key={i}
                  className="w-1 h-1 rounded-full"
                  style={{ background: config?.color ?? 'var(--color-accent-violet)' }}
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                />
              ))}
            </span>
          )}
        </div>
        {message && (
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {message}
          </p>
        )}
      </div>
    </motion.div>
  )
}
