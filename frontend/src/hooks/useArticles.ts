import { useState, useCallback, useEffect } from 'react'
import type { Article } from '@/types'
import { fetchArticles } from '@/lib/api'
import { DEMO_ARTICLES } from '@/lib/demo-articles'

export function useArticles() {
  const [articles, setArticles] = useState<Article[]>(DEMO_ARTICLES)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchArticles()
      if (Array.isArray(data) && data.length > 0) {
        setArticles(data)
      }
    } catch {
      // Backend unavailable -- keep demo articles
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return { articles, loading, refresh }
}
