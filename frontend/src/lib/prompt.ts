import type { Keyword } from '@/types'

export function composPrompt(tags: Keyword[]): string {
  if (tags.length === 0) return ''

  const emotions = tags.filter(t => t.category === 'emotions').map(t => t.text)
  const objects  = tags.filter(t => t.category === 'objects').map(t => t.text)
  const trending = tags.filter(t => t.category === 'trending').map(t => t.text)
  const styles   = tags.filter(t => t.category === 'styles').map(t => t.text)
  const memes    = tags.filter(t => t.category === 'memes').map(t => t.text)

  const parts: string[] = []
  const topicParts = [...objects, ...trending].join('、')
  if (topicParts) parts.push(`关于${topicParts}`)
  if (emotions.length) parts.push(`带有${emotions.join('、')}的情绪`)
  if (memes.length) parts.push(`融入${memes.join('、')}元素`)

  const styleStr = styles.length ? `${styles.join('+')}风格的` : ''
  const bodyStr = parts.length ? parts.join('，') : '一个有趣话题'

  return `写一篇${styleStr}公众号文章，${bodyStr}`
}
