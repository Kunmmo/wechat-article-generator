import { motion } from 'framer-motion'
import type { Article } from '@/types'

interface Props {
  article: Article
  onClick: () => void
  index: number
}

export default function ArticleCard({ article, onClick, index }: Props) {
  const scoreColor = article.score >= 8 ? '#10b981' : article.score >= 7 ? '#f97316' : '#ef4444'
  const date = new Date(article.createdAt).toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
  })

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, type: 'spring', stiffness: 300, damping: 25 }}
      whileHover={{ y: -4, scale: 1.02 }}
      onClick={onClick}
      className="cursor-pointer rounded-xl overflow-hidden group"
      style={{
        background: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Thumbnail area */}
      <div className="relative h-36 overflow-hidden"
           style={{ background: 'var(--color-bg-elevated)' }}>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-4xl opacity-20">📄</span>
        </div>
        <div className="absolute inset-0 bg-gradient-to-t from-[var(--color-bg-surface)] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-center pb-3">
          <span className="text-xs font-medium px-3 py-1 rounded-full"
                style={{ background: 'var(--color-accent-indigo)', color: 'white' }}>
            预览
          </span>
        </div>
      </div>

      <div className="p-3">
        <h3 className="text-sm font-medium truncate" style={{ color: 'var(--color-text-primary)' }}>
          {article.title}
        </h3>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {date}
          </span>
          <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                style={{ background: `${scoreColor}15`, color: scoreColor }}>
            {article.score.toFixed(1)}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
