const BASE = ''

export async function fetchKeywords() {
  const res = await fetch(`${BASE}/api/keywords`)
  if (!res.ok) throw new Error(`Failed to fetch keywords: ${res.status}`)
  return res.json()
}

export async function startGeneration(topic: string, maxRounds = 3, format = 'html') {
  const res = await fetch(`${BASE}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, max_rounds: maxRounds, format }),
  })
  if (!res.ok) throw new Error(`Failed to start generation: ${res.status}`)
  return res.json() as Promise<{ task_id: string }>
}

export async function fetchArticles() {
  const res = await fetch(`${BASE}/api/articles`)
  if (!res.ok) throw new Error(`Failed to fetch articles: ${res.status}`)
  return res.json()
}

export async function fetchArticlePreview(id: string): Promise<string> {
  const res = await fetch(`${BASE}/api/articles/${id}/preview`)
  if (!res.ok) throw new Error(`Failed to fetch preview: ${res.status}`)
  return res.text()
}

export function getProgressSSEUrl(taskId: string) {
  return `${BASE}/api/progress/${taskId}`
}

export function getArticleDownloadUrl(id: string) {
  return `${BASE}/api/articles/${id}/download`
}
