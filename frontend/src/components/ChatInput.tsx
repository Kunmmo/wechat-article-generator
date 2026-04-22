import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import type { Keyword } from '@/types'
import { composPrompt } from '@/lib/prompt'
import SelectedTags from './SelectedTags'

interface Props {
  tags: Keyword[]
  onRemoveTag: (text: string) => void
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ tags, onRemoveTag, onSend, disabled }: Props) {
  const [text, setText] = useState('')
  const autoPrompt = composPrompt(tags)

  useEffect(() => {
    if (tags.length > 0 && text === '') {
      setText(autoPrompt)
    }
  }, [autoPrompt])

  const handleSend = () => {
    const msg = text.trim() || autoPrompt
    if (!msg) return
    onSend(msg)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="w-full">
      {tags.length > 0 && (
        <div className="mb-2">
          <SelectedTags tags={tags} onRemove={onRemoveTag} compact />
        </div>
      )}
      <div className="flex items-end gap-3 p-3 rounded-2xl"
           style={{
             background: 'var(--color-bg-elevated)',
             border: '1px solid var(--color-border)',
           }}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={autoPrompt || '描述你想要的公众号文章...'}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent border-none outline-none resize-none text-sm leading-6 placeholder:text-[var(--color-text-muted)]"
          style={{
            color: 'var(--color-text-primary)',
            minHeight: '24px',
            maxHeight: '120px',
          }}
          onInput={(e) => {
            const el = e.currentTarget
            el.style.height = 'auto'
            el.style.height = Math.min(el.scrollHeight, 120) + 'px'
          }}
        />
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.92 }}
          onClick={handleSend}
          disabled={disabled || (!text.trim() && !autoPrompt)}
          className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-opacity disabled:opacity-30"
          style={{
            background: 'linear-gradient(135deg, var(--color-accent-indigo), var(--color-accent-pink))',
          }}
        >
          {disabled ? (
            <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"
                 strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </motion.button>
      </div>
    </div>
  )
}
