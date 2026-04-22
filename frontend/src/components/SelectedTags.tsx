import { motion, AnimatePresence } from 'framer-motion'
import type { Keyword } from '@/types'
import { CATEGORY_COLORS } from '@/types'

interface Props {
  tags: Keyword[]
  onRemove: (text: string) => void
  compact?: boolean
}

export default function SelectedTags({ tags, onRemove, compact = false }: Props) {
  if (tags.length === 0 && compact) return null

  return (
    <div className={`flex flex-wrap gap-2 ${compact ? '' : 'min-h-[36px] items-center'}`}>
      <AnimatePresence mode="popLayout">
        {tags.map(tag => {
          const color = CATEGORY_COLORS[tag.category]
          return (
            <motion.span
              key={tag.text}
              layout
              initial={{ opacity: 0, scale: 0.5, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.3, y: 10 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              className="inline-flex items-center gap-1.5 rounded-full cursor-default"
              style={{
                padding: compact ? '2px 10px' : '4px 14px',
                fontSize: compact ? '12px' : '13px',
                background: `${color}18`,
                border: `1px solid ${color}40`,
                color,
              }}
            >
              {tag.text}
              <button
                onClick={(e) => { e.stopPropagation(); onRemove(tag.text) }}
                className="ml-0.5 opacity-60 hover:opacity-100 transition-opacity"
                style={{ color }}
              >
                <svg width={compact ? 12 : 14} height={compact ? 12 : 14} viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" strokeWidth="2.5"
                     strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </motion.span>
          )
        })}
      </AnimatePresence>
      {tags.length === 0 && !compact && (
        <span className="text-sm text-[var(--color-text-muted)] italic">
          点击上方词云，选择你的灵感关键词...
        </span>
      )}
    </div>
  )
}
