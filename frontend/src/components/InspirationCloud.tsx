import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Keyword, KeywordCategory } from '@/types'
import { CATEGORY_COLORS } from '@/types'

interface Props {
  keywords: Keyword[]
  selectedTags: Keyword[]
  onSelectTag: (kw: Keyword) => void
}

interface PlacedWord {
  keyword: Keyword
  x: number
  y: number
  fontSize: number
  rotation: number
  opacity: number
}

function layoutWords(keywords: Keyword[], width: number, height: number): PlacedWord[] {
  const placed: PlacedWord[] = []
  const cx = width / 2
  const cy = height / 2

  const sorted = [...keywords].sort((a, b) => (b.weight ?? 5) - (a.weight ?? 5))

  for (let i = 0; i < sorted.length; i++) {
    const kw = sorted[i]
    const weight = kw.weight ?? 5
    const fontSize = 14 + weight * 2.5

    // Spiral placement
    const angle = i * 0.8
    const radius = 30 + i * 12
    const x = cx + Math.cos(angle) * radius * (width / 800)
    const y = cy + Math.sin(angle) * radius * (height / 500)

    placed.push({
      keyword: kw,
      x: Math.max(40, Math.min(width - 40, x)),
      y: Math.max(30, Math.min(height - 30, y)),
      fontSize,
      rotation: (Math.random() - 0.5) * 12,
      opacity: 0.6 + (weight / 10) * 0.4,
    })
  }
  return placed
}

export default function InspirationCloud({ keywords, selectedTags, onSelectTag }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 900, height: 420 })
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(([entry]) => {
      setDimensions({
        width: entry.contentRect.width,
        height: Math.max(360, entry.contentRect.height),
      })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Auto-refresh a subset every 15s
  useEffect(() => {
    const timer = setInterval(() => setRefreshKey(k => k + 1), 15000)
    return () => clearInterval(timer)
  }, [])

  const selectedTexts = useMemo(
    () => new Set(selectedTags.map(t => t.text)),
    [selectedTags]
  )

  const visibleKeywords = useMemo(() => {
    let pool = keywords.filter(kw => !selectedTexts.has(kw.text))
    // Shuffle a portion on refresh
    if (refreshKey > 0) {
      const arr = [...pool]
      for (let i = arr.length - 1; i > arr.length * 0.7; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[arr[i], arr[j]] = [arr[j], arr[i]]
      }
      pool = arr
    }
    return pool.slice(0, 40)
  }, [keywords, selectedTexts, refreshKey])

  const placed = useMemo(
    () => layoutWords(visibleKeywords, dimensions.width, dimensions.height),
    [visibleKeywords, dimensions]
  )

  const handleClick = useCallback((kw: Keyword) => {
    onSelectTag(kw)
  }, [onSelectTag])

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded-2xl overflow-hidden"
      style={{
        height: '420px',
        background: 'radial-gradient(ellipse at center, rgba(99,102,241,0.06) 0%, transparent 70%)',
      }}
    >
      {/* Category legend */}
      <div className="absolute top-4 right-4 flex gap-3 z-10 text-xs">
        {(Object.entries(CATEGORY_COLORS) as [KeywordCategory, string][]).map(([cat, color]) => (
          <span key={cat} className="flex items-center gap-1 opacity-60">
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            {cat === 'emotions' ? '情绪' : cat === 'objects' ? '事物' : cat === 'trending' ? '时事' : cat === 'styles' ? '风格' : '梗'}
          </span>
        ))}
      </div>

      <AnimatePresence mode="popLayout">
        {placed.map((w, i) => {
          const color = CATEGORY_COLORS[w.keyword.category]
          const isHovered = hoveredId === w.keyword.text
          return (
            <motion.button
              key={w.keyword.text}
              layout
              initial={{ opacity: 0, scale: 0.3 }}
              animate={{
                opacity: w.opacity,
                scale: isHovered ? 1.25 : 1,
                x: w.x - dimensions.width / 2,
                y: w.y - dimensions.height / 2,
              }}
              exit={{ opacity: 0, scale: 0.2, transition: { duration: 0.3 } }}
              transition={{
                type: 'spring',
                stiffness: 200,
                damping: 20,
                delay: i * 0.015,
              }}
              whileHover={{ scale: 1.3 }}
              whileTap={{ scale: 0.85 }}
              onClick={() => handleClick(w.keyword)}
              onMouseEnter={() => setHoveredId(w.keyword.text)}
              onMouseLeave={() => setHoveredId(null)}
              className="absolute cursor-pointer select-none font-medium transition-[text-shadow] duration-200"
              style={{
                left: '50%',
                top: '50%',
                fontSize: `${w.fontSize}px`,
                color,
                textShadow: isHovered ? `0 0 20px ${color}88, 0 0 40px ${color}44` : 'none',
                transform: `rotate(${w.rotation}deg)`,
              }}
            >
              {w.keyword.text}
            </motion.button>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
