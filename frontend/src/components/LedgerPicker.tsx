import { useEffect, useState } from 'react'

import { ApiError, api } from '../lib/api.ts'
import type { Ledger, LedgerState } from '../lib/types.ts'
import { Badge } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

type LedgersState =
  | { kind: 'loading' }
  | { kind: 'ready'; ledgers: Ledger[] }
  | { kind: 'error'; message: string }

interface LedgerPickerProps {
  ledger: LedgerState | null
  editable: boolean
  /** Saves the chosen code. Rejects with an `ApiError` on failure. */
  onSelect: (code: string) => Promise<void>
}

export function LedgerPicker({ ledger, editable, onSelect }: LedgerPickerProps) {
  const [attempt, setAttempt] = useState(0)
  const [answer, setAnswer] = useState<
    { attempt: number; ledgers: Ledger[] } | { attempt: number; message: string } | null
  >(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .ledgers()
      .then((list) => {
        if (!cancelled) setAnswer({ attempt, ledgers: list })
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          const message = failure instanceof Error ? failure.message : 'Unknown error'
          setAnswer({ attempt, message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  const ledgers: LedgersState =
    answer === null || answer.attempt !== attempt
      ? { kind: 'loading' }
      : 'message' in answer
        ? { kind: 'error', message: answer.message }
        : { kind: 'ready', ledgers: answer.ledgers }

  async function choose(code: string) {
    if (code === '') return
    setSaving(true)
    setError(null)
    try {
      await onSelect(code)
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : 'Could not save the ledger.')
    } finally {
      setSaving(false)
    }
  }

  const list = ledgers.kind === 'ready' ? ledgers.ledgers : []
  const nameOf = (code: string | null) => list.find((l) => l.code === code)?.name
  const suggested = ledger?.suggested_code ?? null
  const selected = ledger?.selected_code ?? null

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Ledger</h2>
        {selected !== null ? (
          <Badge tone="success">Selected</Badge>
        ) : (
          <Badge tone="warning">Not selected</Badge>
        )}
        {ledger?.overridden && <Badge tone="info">Overridden</Badge>}
      </div>

      {ledger === null ? (
        <p className="text-sm text-zinc-500">No ledger suggestion for this document.</p>
      ) : (
        <div className="rounded-md bg-zinc-50 p-2.5 text-sm">
          <p className="text-xs font-medium text-zinc-500">Suggested</p>
          {suggested !== null ? (
            <p>
              <span className="font-medium">
                {suggested} {nameOf(suggested)}
              </span>
            </p>
          ) : (
            <p className="text-zinc-600">No suggestion. Choose a ledger below.</p>
          )}
          <p className="mt-0.5 text-zinc-600">{ledger.reason}</p>
        </div>
      )}

      {ledgers.kind === 'loading' && <p className="text-sm text-zinc-500">Loading ledgers…</p>}
      {ledgers.kind === 'error' && (
        <p role="alert" className="text-sm text-red-700">
          Could not load the ledgers: {ledgers.message}
        </p>
      )}
      {ledgers.kind === 'error' && (
        <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </Button>
      )}

      {ledgers.kind === 'ready' && (
        <div className="space-y-2">
          <label htmlFor="ledger-select" className="block text-xs font-medium text-zinc-600">
            Ledger for this document
          </label>
          <select
            id="ledger-select"
            value={selected ?? ''}
            disabled={!editable || saving}
            onChange={(event) => void choose(event.target.value)}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm disabled:bg-zinc-100"
          >
            <option value="" disabled>
              Choose a ledger…
            </option>
            {ledgers.ledgers.map((l) => (
              <option key={l.code} value={l.code}>
                {l.code} · {l.name}
              </option>
            ))}
          </select>
          {editable && suggested !== null && selected !== suggested && (
            <Button
              variant="secondary"
              loading={saving}
              onClick={() => void choose(suggested)}
            >
              Use suggestion ({suggested})
            </Button>
          )}
          {!editable && <p className="text-xs text-zinc-500">This review is decided and locked.</p>}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
    </Card>
  )
}
