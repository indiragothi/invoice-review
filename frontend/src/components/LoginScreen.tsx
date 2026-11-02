import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '../lib/api.ts'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

export function LoginScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (password === '') return
    setBusy(true)
    setError(null)
    try {
      await api.login(password)
      onSignedIn()
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center gap-6">
      <header>
        <p className="text-sm font-medium text-indigo-600">Mehta &amp; Associates</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Invoice Review</h1>
        <p className="mt-2 text-zinc-600">This demo is protected. Enter the access password.</p>
      </header>
      <Card>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <label className="block text-sm font-medium text-zinc-800" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={error !== null}
            aria-describedby={error ? 'password-error' : undefined}
            className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-indigo-600"
          />
          {error && (
            <p id="password-error" role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
          <Button type="submit" loading={busy} disabled={password === ''} className="w-full">
            Sign in
          </Button>
        </form>
      </Card>
      <p className="text-xs text-zinc-500">
        Use fictional or sample documents only. Free-tier AI services may keep what you send.
      </p>
    </div>
  )
}
