import { useEffect, useState } from 'react'

import { InboxScreen } from './components/InboxScreen.tsx'
import { LoginScreen } from './components/LoginScreen.tsx'
import { ProcessingScreen } from './components/ProcessingScreen.tsx'
import type { ProcessingState } from './components/ProcessingScreen.tsx'
import { ReviewScreen } from './components/ReviewScreen.tsx'
import { UploadScreen } from './components/UploadScreen.tsx'
import { WelcomeScreen } from './components/WelcomeScreen.tsx'
import { Button } from './components/ui/Button.tsx'
import { ApiError, api, setUnauthorizedHandler } from './lib/api.ts'
import type { Client, DocumentRecord } from './lib/types.ts'

interface Pending {
  file: File
  client: Client
  /** Set once the server has stored the file but the provider failed: retry, not re-upload. */
  savedId: string | null
}

type Screen =
  | { name: 'welcome' }
  | { name: 'upload' }
  | { name: 'inbox' }
  | { name: 'processing'; pending: Pending; state: ProcessingState }
  | { name: 'result'; document: DocumentRecord }

function Workspace() {
  const [screen, setScreen] = useState<Screen>({ name: 'welcome' })

  async function run(pending: Pending) {
    setScreen({ name: 'processing', pending, state: { kind: 'working' } })
    try {
      const document =
        pending.savedId === null
          ? await api.upload(pending.file, pending.client.id)
          : await api.retry(pending.savedId)
      setScreen({ name: 'result', document })
    } catch (error) {
      const failure = error instanceof ApiError ? error : null
      const savedId = failure?.document?.id ?? pending.savedId
      const providerBusy = failure?.isProviderBusy ?? false
      setScreen({
        name: 'processing',
        pending: { ...pending, savedId },
        state: {
          kind: 'failed',
          message: failure?.detail ?? 'Something went wrong.',
          providerBusy,
          // A provider failure or a lost connection may pass; a rejected file will not.
          canRetry: providerBusy || failure?.status === 0,
        },
      })
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl p-6">
      {screen.name === 'welcome' && (
        <WelcomeScreen
          onStart={() => setScreen({ name: 'upload' })}
          onInbox={() => setScreen({ name: 'inbox' })}
        />
      )}
      {screen.name === 'upload' && (
        <UploadScreen
          onSubmit={(file, client) => void run({ file, client, savedId: null })}
          onBack={() => setScreen({ name: 'welcome' })}
        />
      )}
      {screen.name === 'inbox' && (
        <InboxScreen
          onOpen={(document) => setScreen({ name: 'result', document })}
          onUpload={() => setScreen({ name: 'upload' })}
          onHome={() => setScreen({ name: 'welcome' })}
        />
      )}
      {screen.name === 'processing' && (
        <ProcessingScreen
          filename={screen.pending.file.name}
          clientName={screen.pending.client.name}
          state={screen.state}
          onRetry={() => void run(screen.pending)}
          onBack={() => setScreen({ name: 'upload' })}
        />
      )}
      {screen.name === 'result' && (
        <ReviewScreen
          key={screen.document.id}
          initial={screen.document}
          onUpload={() => setScreen({ name: 'upload' })}
          onInbox={() => setScreen({ name: 'inbox' })}
          onDeleted={() => setScreen({ name: 'inbox' })}
        />
      )}
    </main>
  )
}

type Access =
  | { kind: 'checking' }
  | { kind: 'unreachable'; message: string }
  | { kind: 'login' }
  /** `gate` is true when the password gate is on, so a sign-out button makes sense. */
  | { kind: 'in'; gate: boolean }

export default function App() {
  const [access, setAccess] = useState<Access>({ kind: 'checking' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .session()
      .then((session) => {
        if (cancelled) return
        setAccess(
          session.authenticated
            ? { kind: 'in', gate: session.gate_enabled }
            : { kind: 'login' },
        )
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'Unknown error'
        setAccess({ kind: 'unreachable', message })
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  // A protected call answering 401 means the session ended: back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setAccess({ kind: 'login' }))
    return () => setUnauthorizedHandler(null)
  }, [])

  async function signOut() {
    try {
      await api.logout()
    } finally {
      setAccess({ kind: 'login' })
    }
  }

  if (access.kind === 'checking') {
    return <p className="p-6 text-sm text-zinc-500">Checking sign-in…</p>
  }
  if (access.kind === 'unreachable') {
    return (
      <main className="mx-auto max-w-xl p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium">Backend not reachable</p>
          <p className="mt-1">{access.message}</p>
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => {
              setAccess({ kind: 'checking' })
              setAttempt((n) => n + 1)
            }}
          >
            Try again
          </Button>
        </div>
      </main>
    )
  }
  if (access.kind === 'login') {
    return (
      <main className="mx-auto min-h-screen max-w-5xl p-6">
        <LoginScreen onSignedIn={() => setAccess({ kind: 'in', gate: true })} />
      </main>
    )
  }
  return (
    <>
      {access.gate && (
        <div className="mx-auto flex max-w-5xl justify-end px-6 pt-4">
          <Button variant="ghost" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      )}
      <Workspace />
    </>
  )
}
