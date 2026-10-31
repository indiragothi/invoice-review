import { useEffect, useState } from 'react'

import { api } from '../lib/api.ts'
import type { HealthResponse } from '../lib/types.ts'

type State =
  | { kind: 'loading' }
  | { kind: 'ok'; health: HealthResponse }
  | { kind: 'error'; message: string }

export function BackendStatus() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((health) => {
        if (!cancelled) setState({ kind: 'ok', health })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Unknown error'
          setState({ kind: 'error', message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.kind === 'loading') {
    return <p className="text-sm text-zinc-500">Checking backend…</p>
  }

  if (state.kind === 'error') {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-medium">Backend not reachable</p>
        <p className="mt-1">{state.message}. Is the backend running on port 8000?</p>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
      <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" aria-hidden />
      <p>
        Backend connected · <span className="font-medium">{state.health.llm_provider}</span> ·{' '}
        <code className="rounded bg-white px-1.5 py-0.5">{state.health.model}</code>
      </p>
    </div>
  )
}
