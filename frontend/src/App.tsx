import { useState, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import type { Keyword, Article } from '@/types'
import { useArticles } from '@/hooks/useArticles'
import { useKeywords } from '@/hooks/useKeywords'
import { useTheme } from '@/hooks/useTheme'
import AppHeader from '@/components/AppHeader'
import InspirationCloud from '@/components/InspirationCloud'
import SelectedTags from '@/components/SelectedTags'
import CreationChat from '@/components/CreationChat'
import WorkshopGallery from '@/components/WorkshopGallery'
import ArticlePreview from '@/components/ArticlePreview'

export default function App() {
  const [selectedTags, setSelectedTags] = useState<Keyword[]>([])
  const [previewId, setPreviewId] = useState<string | null>(null)
  const { articles, loading, refresh } = useArticles()
  const keywords = useKeywords()
  const { theme, toggle: toggleTheme } = useTheme()

  const previewArticle = useMemo<Article | null>(
    () => articles.find(a => a.id === previewId) ?? null,
    [articles, previewId]
  )

  const handleSelectTag = useCallback((kw: Keyword) => {
    setSelectedTags(prev => {
      if (prev.some(t => t.text === kw.text)) return prev
      return [...prev, kw]
    })
  }, [])

  const handleRemoveTag = useCallback((text: string) => {
    setSelectedTags(prev => prev.filter(t => t.text !== text))
  }, [])

  const scrollToCreate = () => {
    document.getElementById('creation')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <>
      <AppHeader theme={theme} onToggleTheme={toggleTheme} />

      {/* ZONE 1: Inspiration */}
      <section id="inspiration" className="zone" style={{ paddingTop: '5rem' }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
          className="w-full max-w-4xl"
        >
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold mb-2">
              <span className="gradient-text">探索灵感</span>
            </h2>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              点击词云中的关键词，组合你的创作灵感
            </p>
          </div>

          <InspirationCloud
            keywords={keywords}
            selectedTags={selectedTags}
            onSelectTag={handleSelectTag}
          />

          <div className="mt-6 px-4">
            <SelectedTags tags={selectedTags} onRemove={handleRemoveTag} />
          </div>

          {selectedTags.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 text-center"
            >
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={scrollToCreate}
                className="px-6 py-2.5 rounded-xl text-sm font-medium"
                style={{
                  background: 'linear-gradient(135deg, var(--color-accent-indigo), var(--color-accent-violet))',
                  color: 'white',
                }}
              >
                开始创作 ↓
              </motion.button>
            </motion.div>
          )}
        </motion.div>
      </section>

      <div className="zone-divider" />

      {/* ZONE 2: Creation */}
      <section id="creation" className="zone">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.6 }}
          className="w-full max-w-4xl"
        >
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold mb-2">
              <span className="gradient-text">聊天创作</span>
            </h2>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              描述你的创意，多智能体协作为你撰写
            </p>
          </div>

          <CreationChat
            tags={selectedTags}
            onRemoveTag={handleRemoveTag}
            onPreviewArticle={setPreviewId}
            onArticleGenerated={refresh}
          />
        </motion.div>
      </section>

      <div className="zone-divider" />

      {/* ZONE 3: Workshop */}
      <section id="workshop" className="zone" style={{ justifyContent: 'flex-start', paddingTop: '3rem' }}>
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.6 }}
          className="w-full max-w-5xl"
        >
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold mb-2">
              <span className="gradient-text">作品工坊</span>
            </h2>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              管理和预览你的所有公众号文章
            </p>
          </div>

          <WorkshopGallery
            articles={articles}
            loading={loading}
            onPreview={setPreviewId}
            onScrollToCreate={scrollToCreate}
          />
        </motion.div>
      </section>

      {/* Article Preview Modal */}
      <ArticlePreview
        article={previewArticle}
        onClose={() => setPreviewId(null)}
      />
    </>
  )
}
