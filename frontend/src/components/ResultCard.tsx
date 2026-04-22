import { motion } from 'framer-motion'
import type { ArticleResultMeta } from '@/types'
import { getArticleDownloadUrl } from '@/lib/api'

interface Props {
  meta: ArticleResultMeta
  onPreview?: (articleId: string) => void
}

export default function ResultCard({ meta, onPreview }: Props) {
  const scoreColor = meta.score >= 8 ? '#10b981' : meta.score >= 7 ? '#f97316' : '#ef4444'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'var(--color-bg-elevated)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Gradient accent top bar */}
      <div className="h-1"
           style={{ background: 'linear-gradient(90deg, var(--color-accent-indigo), var(--color-accent-violet), var(--color-accent-pink))' }} />

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs mb-1" style={{ color: 'var(--color-accent-green)' }}>
              文章已生成
            </p>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {meta.title || '公众号文章'}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs px-2 py-1 rounded-lg"
                  style={{ background: `${scoreColor}15`, color: scoreColor, border: `1px solid ${scoreColor}30` }}>
              {meta.score.toFixed(1)}
            </span>
            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {meta.rounds} 轮
            </span>
          </div>
        </div>

        <div className="flex gap-2 mt-3">
          <button
            onClick={() => onPreview?.(meta.articleId)}
            className="flex-1 py-2 rounded-lg text-xs font-medium transition-colors duration-200"
            style={{
              background: 'var(--color-accent-indigo)',
              color: 'white',
            }}
          >
            预览文章
          </button>
          <a
            href={getArticleDownloadUrl(meta.articleId)}
            download
            className="flex-1 py-2 rounded-lg text-xs font-medium text-center transition-colors duration-200"
            style={{
              background: 'transparent',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
            }}
          >
            下载 HTML
          </a>
        </div>
      </div>
    </motion.div>
  )
}
