import { useState } from 'react'

import { ApiError, api } from '../lib/api.ts'
import { Button } from './ui/Button.tsx'
import { ConfirmDialog } from './ui/ConfirmDialog.tsx'

interface DeleteReviewProps {
  documentId: string
  filename: string
  /** Called after the server deleted the review and its files. */
  onDeleted: () => void
}

export function DeleteReview({ documentId, filename, onDeleted }: DeleteReviewProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await api.deleteDocument(documentId)
      onDeleted()
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : 'Could not delete the review.')
      setBusy(false)
    }
  }

  return (
    <>
      <Button variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setOpen(true)}>
        Delete
      </Button>
      <ConfirmDialog
        open={open}
        title="Delete this review?"
        confirmLabel="Delete"
        destructive
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => {
          setOpen(false)
          setError(null)
        }}
      >
        <p>
          <span className="font-medium">{filename}</span>, its fields, decision and the uploaded
          file will be removed. This cannot be undone.
        </p>
        {error && (
          <p role="alert" className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-red-800">
            {error}
          </p>
        )}
      </ConfirmDialog>
    </>
  )
}
