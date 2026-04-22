import { useCallback, useRef } from 'react'
import { getProgressSSEUrl } from '@/lib/api'
import type { WorkflowSSEEvent } from '@/types'

export function useSSE(onEvent: (e: WorkflowSSEEvent) => void, onDone: () => void) {
  const abortRef = useRef<AbortController | null>(null)

  const connect = useCallback((taskId: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const url = getProgressSSEUrl(taskId)

    fetch(url, {
      headers: { 'Accept': 'application/json' },
      signal: controller.signal,
    }).then(async (res) => {
      if (!res.ok || !res.body) {
        onDone()
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6)
            if (currentEvent === 'done') {
              onDone()
              return
            }
            try {
              const data = JSON.parse(raw)
              const eventName = currentEvent || data.type || 'progress'
              onEvent({ event: eventName, data })
            } catch {
              onEvent({ event: currentEvent || 'progress', data: { message: raw } })
            }
            currentEvent = ''
          }
        }
      }
      onDone()
    }).catch(() => {
      onDone()
    })
  }, [onEvent, onDone])

  const disconnect = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  return { connect, disconnect }
}
