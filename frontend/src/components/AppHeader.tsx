import { motion } from 'framer-motion'
import type { ThemeMode } from '@/types'

interface Props {
  theme: ThemeMode
  onToggleTheme: () => void
}

export default function AppHeader({ theme, onToggleTheme }: Props) {
  return (
    <motion.header
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className="fixed top-0 left-0 right-0 z-50 glass"
      style={{ borderBottom: '1px solid var(--color-glass-border)' }}
    >
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{
                 background: 'linear-gradient(135deg, var(--color-accent-indigo), var(--color-accent-pink))',
               }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"
                 strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h1 className="text-lg font-bold">
            <span className="gradient-text">VibePub</span>
            <span className="text-[var(--color-text-muted)] font-normal text-sm ml-2">灵感造物</span>
          </h1>
        </div>

        <div className="flex items-center gap-5">
          <nav className="flex items-center gap-4 text-sm text-[var(--color-text-secondary)]">
            <a href="#inspiration" className="hover:text-[var(--color-text-primary)] transition-colors duration-200">灵感</a>
            <a href="#creation" className="hover:text-[var(--color-text-primary)] transition-colors duration-200">创作</a>
            <a href="#workshop" className="hover:text-[var(--color-text-primary)] transition-colors duration-200">工坊</a>
          </nav>

          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={onToggleTheme}
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors duration-300"
            style={{
              background: 'var(--color-bg-elevated)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-secondary)',
            }}
            title={theme === 'dark' ? '切换亮色模式' : '切换暗色模式'}
          >
            {theme === 'dark' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </motion.button>
        </div>
      </div>
    </motion.header>
  )
}
