import { useState } from 'react'

import { ApiError } from '../lib/api.ts'
import type { Decision, DocumentStatus } from '../lib/types.ts'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'
import { ConfirmDialog } from './ui/ConfirmDialog.tsx'

interface DecisionBarProps {
  status: DocumentStatus
  /** Records the decision. Rejects with an `ApiError` (409 carries the reasons). */
  onDecide: (decision: Decision) => Promise<void>
}

export function DecisionBar({ status, onDecide }: DecisionBarProps) {
  const [asking, setAsking] = useState<Decision | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (status === 'approved' || status === 'rejected') {
    return (
      <Card
        role="status"
        className={`text-sm ${status === 'approved' ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'bg-zinc-50 text-zinc-700'}`}
      >
        {status === 'approved'
          ? 'Approved. This review is locked and is included in the export.'
          : 'Rejected. This review is locked and is not exported.'}
      </Card>
    )
  }

  // Only a finished review can be decided; the server enforces the same.
  if (status !== 'ready' && status !== 'needs_review') return null

  async function confirm() {
    if (asking === null) return
    setBusy(true)
    setError(null)
    try {
      await onDecide(asking)
    } catch (failure) {
      // The reasons come from the server (open blocking errors, no ledger selected, ...).
      setError(failure instanceof ApiError ? failure.detail : 'Could not save the decision.')
    } finally {
      setBusy(false)
      setAsking(null)
    }
  }

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-zinc-600">
          {status === 'ready'
            ? 'No blocking errors. Pick a ledger, then approve.'
            : 'This review has blocking errors. Fix them before it can be approved.'}
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setAsking('rejected')} disabled={busy}>
            Reject
          </Button>
          <Button onClick={() => setAsking('approved')} disabled={busy}>
            Approve
          </Button>
        </div>
      </div>
      {error && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-2.5 text-sm text-red-800">
          Not approved: {error}
        </p>
      )}
      <ConfirmDialog
        open={asking !== null}
        title={asking === 'rejected' ? 'Reject this document?' : 'Approve this document?'}
        confirmLabel={asking === 'rejected' ? 'Reject' : 'Approve'}
        destructive={asking === 'rejected'}
        busy={busy}
        onConfirm={() => void confirm()}
        onCancel={() => setAsking(null)}
      >
        {asking === 'rejected'
          ? 'It will be locked and left out of the export. This cannot be undone.'
          : 'It will be locked: no more edits, and it will be included in the export. This cannot be undone.'}
      </ConfirmDialog>
    </Card>
  )
}
