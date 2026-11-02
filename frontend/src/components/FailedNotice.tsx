import { useState } from 'react'

import { ApiError, api } from '../lib/api.ts'
import type { DocumentRecord } from '../lib/types.ts'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

interface FailedNoticeProps {
  record: DocumentRecord
  /** A new answer from the server (after a retry) replaces the review on the screen. */
  onRecord: (record: DocumentRecord) => void
}

/** Shown instead of the fields when a review has none. A provider failure (busy, quota, network)
 * can be retried on the saved file; a rejected file (not an invoice) cannot. */
export function FailedNotice({ record, onRecord }: FailedNoticeProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const failed = record.status === 'failed'
  const providerFailed = failed && record.pipeline_run?.error_kind === 'provider'

  async function retry() {
    setBusy(true)
    setError(null)
    try {
      onRecord(await api.retry(record.id))
    } catch (failure) {
      const apiError = failure instanceof ApiError ? failure : null
      if (apiError?.document) onRecord(apiError.document)
      setError(apiError?.detail ?? 'Could not try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card role="alert" className="space-y-2 text-sm">
      <p className="font-medium text-red-800">
        {providerFailed
          ? 'The AI service was busy, so this document was not read'
          : failed
            ? 'This document could not be processed'
            : 'This document has no extracted fields'}
      </p>
      {record.error_message && <p className="text-zinc-700">{record.error_message}</p>}
      {providerFailed && (
        <>
          <p className="text-zinc-500">
            The file is saved. The free tier has limits; wait a minute and try again. A retry costs
            the same model calls as an upload.
          </p>
          <Button onClick={() => void retry()} loading={busy}>
            Try again
          </Button>
        </>
      )}
      {error && <p className="text-red-700">{error}</p>}
    </Card>
  )
}
