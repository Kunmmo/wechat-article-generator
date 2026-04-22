import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Article } from '@/types'

interface Props {
  article: Article | null
  onClose: () => void
}

export default function ArticlePreview({ article, onClose }: Props) {
  const [html, setHtml] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!article) { setHtml(null); return }
    setLoading(true)
    fetch(article.previewUrl)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.text()
      })
      .then(setHtml)
      .catch(() => setHtml('<p style="padding:2rem;color:#999;text-align:center">无法加载预览</p>'))
      .finally(() => setLoading(false))
  }, [article])

  return (
    <AnimatePresence>
      {article && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-6"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, y: 30 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 30 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-lg flex flex-col"
            style={{ maxHeight: '90vh' }}
          >
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-3 rounded-t-2xl"
                 style={{ background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}>
              <span className="text-sm font-medium truncate pr-4" style={{ color: 'var(--color-text-primary)' }}>
                {article.title}
              </span>
              <div className="flex items-center gap-2 flex-shrink-0">
                <a
                  href={article.downloadUrl}
                  download
                  className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                  style={{ background: 'var(--color-bg-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
                >
                  下载
                </a>
                <button
                  onClick={onClose}
                  className="w-7 h-7 rounded-lg flex items-center justify-center transition-colors"
                  style={{ background: 'var(--color-bg-surface)', color: 'var(--color-text-secondary)' }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Phone frame */}
            <div className="flex-1 overflow-hidden rounded-b-2xl"
                 style={{
                   background: '#ffffff',
                   border: '1px solid var(--color-border)',
                   borderTop: 'none',
                 }}>
              {loading ? (
                <div className="h-96 flex items-center justify-center">
                  <div className="w-6 h-6 border-2 border-[var(--color-accent-violet)] border-t-transparent rounded-full animate-spin" />
                </div>
              ) : html ? (
                <iframe
                  srcDoc={html}
                  title="Article Preview"
                  className="w-full border-none"
                  style={{ height: 'calc(90vh - 60px)', minHeight: '400px' }}
                  sandbox="allow-same-origin"
                />
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
