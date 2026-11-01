import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

export type ProcessingState =
  | { kind: 'working' }
  | { kind: 'failed'; message: string; providerBusy: boolean; canRetry: boolean }

interface ProcessingScreenProps {
  filename: string
  clientName: string
  state: ProcessingState
  onRetry: () => void
  onBack: () => void
}

export function ProcessingScreen({
  filename,
  clientName,
  state,
  onRetry,
  onBack,
}: ProcessingScreenProps) {
  return (
    <div className="mx-auto max-w-xl space-y-5 pt-16">
      <Card className="space-y-3">
        <p className="text-sm text-zinc-500">
          {filename} · {clientName}
        </p>
        {state.kind === 'working' ? (
          <div role="status" className="flex items-center gap-3">
            <span
              className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent"
              aria-hidden
            />
            <div>
              <p className="font-medium">Reading and checking the document…</p>
              <p className="text-sm text-zinc-500">
                Text and layout are read, fields are extracted, then checked. This takes about 10 to
                20 seconds.
              </p>
            </div>
          </div>
        ) : (
          <div role="alert" className="space-y-3">
            <p className="font-medium text-red-800">
              {state.providerBusy ? 'The AI service is busy' : 'This document could not be processed'}
            </p>
            <p className="text-sm text-zinc-700">{state.message}</p>
            {state.providerBusy && (
              <p className="text-sm text-zinc-500">
                The free tier has limits. Wait a minute and try again; the file is already saved.
              </p>
            )}
            <div className="flex gap-2">
              {state.canRetry && <Button onClick={onRetry}>Try again</Button>}
              <Button variant="secondary" onClick={onBack}>
                Back to upload
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
