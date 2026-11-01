import { useState } from 'react'

import { InboxScreen } from './components/InboxScreen.tsx'
import { ProcessingScreen } from './components/ProcessingScreen.tsx'
import type { ProcessingState } from './components/ProcessingScreen.tsx'
import { ReviewScreen } from './components/ReviewScreen.tsx'
import { UploadScreen } from './components/UploadScreen.tsx'
import { WelcomeScreen } from './components/WelcomeScreen.tsx'
import { ApiError, api } from './lib/api.ts'
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

export default function App() {
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
          record={screen.document}
          onUpload={() => setScreen({ name: 'upload' })}
          onInbox={() => setScreen({ name: 'inbox' })}
        />
      )}
    </main>
  )
}
