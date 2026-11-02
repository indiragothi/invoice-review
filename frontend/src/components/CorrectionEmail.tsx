import { useState } from 'react'

import { ApiError, api } from '../lib/api.ts'
import { Button } from './ui/Button.tsx'
import { Dialog } from './ui/Dialog.tsx'

type Draft =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; subject: string; body: string; basedOn: string }
  | { kind: 'error'; message: string; providerBusy: boolean }

interface CorrectionEmailProps {
  documentId: string
  /** The review's `updated_at`; a draft made from an older state is flagged as out of date. */
  version: string
  /** False when no issue is one the supplier can fix: there is nothing to ask for. */
  available: boolean
}

/** Button + dialog for the supplier correction email. The app only drafts the text; the
 * reviewer copies it into their own mail client. Making a draft costs one model call, so it
 * starts from a click only, and an existing draft is shown again without a new call. */
export function CorrectionEmail({ documentId, version, available }: CorrectionEmailProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>({ kind: 'idle' })
  const [copied, setCopied] = useState<string | null>(null)

  if (!available) return null

  async function generate() {
    setDraft({ kind: 'loading' })
    setCopied(null)
    try {
      const email = await api.correctionEmail(documentId)
      setDraft({ kind: 'ready', subject: email.subject, body: email.body, basedOn: version })
    } catch (failure) {
      const error = failure instanceof ApiError ? failure : null
      setDraft({
        kind: 'error',
        message: error?.detail ?? 'Could not draft the email.',
        providerBusy: error?.isProviderBusy ?? false,
      })
    }
  }

  function openDialog() {
    setOpen(true)
    if (draft.kind === 'idle' || draft.kind === 'error') void generate()
  }

  async function copy(what: 'subject' | 'body' | 'all') {
    if (draft.kind !== 'ready') return
    const text =
      what === 'subject'
        ? draft.subject
        : what === 'body'
          ? draft.body
          : `Subject: ${draft.subject}\n\n${draft.body}`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(what)
    } catch {
      setCopied('failed')
    }
  }

  const stale = draft.kind === 'ready' && draft.basedOn !== version

  return (
    <>
      <Button variant="secondary" onClick={openDialog}>
        Draft correction email
      </Button>
      <Dialog
        open={open}
        title="Correction request to the supplier"
        size="lg"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Close
            </Button>
            {draft.kind === 'ready' && (
              <Button onClick={() => void copy('all')}>
                {copied === 'all' ? 'Copied' : 'Copy email'}
              </Button>
            )}
          </>
        }
      >
        {draft.kind === 'loading' && (
          <div role="status" className="flex items-center gap-3 py-6">
            <span
              className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent"
              aria-hidden
            />
            <p>Drafting the email…</p>
          </div>
        )}

        {draft.kind === 'error' && (
          <div role="alert" className="space-y-3">
            <p className="font-medium text-red-800">
              {draft.providerBusy ? 'The AI service is busy' : 'No draft was made'}
            </p>
            <p>{draft.message}</p>
            <Button onClick={() => void generate()}>Try again</Button>
          </div>
        )}

        {draft.kind === 'ready' && (
          <div className="space-y-3">
            <p className="text-xs text-zinc-500">
              This is only a draft. Nothing is sent from this app: copy it into your own email.
            </p>
            {stale && (
              <p role="status" className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                The fields changed after this draft was made. Make a new draft to match them.
              </p>
            )}
            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="email-subject" className="text-xs font-medium text-zinc-600">
                  Subject
                </label>
                <Button variant="ghost" onClick={() => void copy('subject')}>
                  {copied === 'subject' ? 'Copied' : 'Copy subject'}
                </Button>
              </div>
              <input
                id="email-subject"
                value={draft.subject}
                onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
                className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="email-body" className="text-xs font-medium text-zinc-600">
                  Message
                </label>
                <Button variant="ghost" onClick={() => void copy('body')}>
                  {copied === 'body' ? 'Copied' : 'Copy message'}
                </Button>
              </div>
              <textarea
                id="email-body"
                rows={12}
                value={draft.body}
                onChange={(event) => setDraft({ ...draft, body: event.target.value })}
                className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 font-sans text-sm"
              />
            </div>
            {copied === 'failed' && (
              <p role="alert" className="text-sm text-red-700">
                The browser did not allow copying. Select the text and copy it by hand.
              </p>
            )}
            <Button variant="secondary" onClick={() => void generate()}>
              Make a new draft (1 model call)
            </Button>
          </div>
        )}
      </Dialog>
    </>
  )
}
