import { useState, useEffect } from 'react'
import type { Keyword, KeywordCategory } from '@/types'
import { HARDCODED_KEYWORDS } from '@/lib/keywords'
import { fetchKeywords } from '@/lib/api'

function apiToKeywords(data: Record<string, string[]>): Keyword[] {
  const result: Keyword[] = []
  for (const [category, words] of Object.entries(data)) {
    if (!Array.isArray(words)) continue
    for (const text of words) {
      result.push({
        text,
        category: category as KeywordCategory,
        weight: 3 + Math.floor(Math.random() * 7),
      })
    }
  }
  return result
}

export function useKeywords() {
  const [keywords, setKeywords] = useState<Keyword[]>(HARDCODED_KEYWORDS)

  useEffect(() => {
    fetchKeywords()
      .then(data => {
        const kws = apiToKeywords(data)
        if (kws.length > 0) setKeywords(kws)
      })
      .catch(() => {
        // Use hardcoded keywords as fallback
      })
  }, [])

  return keywords
}
