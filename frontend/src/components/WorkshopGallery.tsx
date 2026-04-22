import { motion } from 'framer-motion'
import type { Article } from '@/types'
import ArticleCard from './ArticleCard'

interface Props {
  articles: Article[]
  loading: boolean
  onPreview: (articleId: string) => void
  onScrollToCreate: () => void
}

export default function WorkshopGallery({ articles, loading, onPreview, onScrollToCreate }: Props) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-6 h-6 border-2 border-[var(--color-accent-violet)] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (articles.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center justify-center py-20 text-center"
      >
        <div className="w-20 h-20 rounded-2xl mb-4 flex items-center justify-center"
             style={{
               background: 'var(--color-bg-elevated)',
               border: '1px solid var(--color-border)',
             }}>
          <span className="text-3xl opacity-30">📚</span>
        </div>
        <h3 className="text-sm font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
          还没有作品
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--color-text-muted)' }}>
          从上方词云获取灵感，开始你的第一篇创作
        </p>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onScrollToCreate}
          className="px-5 py-2 rounded-xl text-xs font-medium"
          style={{
            background: 'linear-gradient(135deg, var(--color-accent-indigo), var(--color-accent-pink))',
            color: 'white',
          }}
        >
          开始创作
        </motion.button>
      </motion.div>
    )
  }

  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
      {articles.map((article, i) => (
        <ArticleCard
          key={article.id}
          article={article}
          index={i}
          onClick={() => onPreview(article.id)}
        />
      ))}
    </div>
  )
}
