import { useState } from 'react'

import { ApiError } from '../lib/api.ts'
import { fieldLabel } from '../lib/fields.ts'
import type { Agreement, FieldSource, Issue, ReviewField } from '../lib/types.ts'
import { Badge } from './ui/Badge.tsx'
import type { Tone } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'

const SOURCE_LABEL: Record<FieldSource, string> = {
  pdf_text: 'PDF text',
  ocr: 'OCR',
  reading_b: '2nd reading',
  human: 'Edited',
}

const AGREEMENT: Record<Agreement, { label: string; tone: Tone } | null> = {
  agree: { label: 'Readings agree', tone: 'success' },
  differ: { label: 'Readings differ', tone: 'warning' },
  filled: { label: 'Filled by 2nd reading', tone: 'info' },
  missing: null,
}

interface FieldRowProps {
  path: string
  field: ReviewField
  selected: boolean
  /** Open issues that point at this field. */
  issues: Issue[]
  /** False once the review is approved or rejected. */
  editable: boolean
  onSelect: (path: string) => void
  /** Saves the corrected text (null clears the value). Rejects with an `ApiError` on failure. */
  onSave: (path: string, text: string | null) => Promise<void>
}

export function FieldRow({
  path,
  field,
  selected,
  issues,
  editable,
  onSelect,
  onSave,
}: FieldRowProps) {
  // null = not editing.
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasError = issues.some((issue) => issue.severity === 'error')
  const agreement = field.agreement ? AGREEMENT[field.agreement] : null
  const editing = draft !== null
  const changedFromModel = field.source === 'human' && field.value !== field.original

  async function save(text: string | null) {
    setSaving(true)
    setError(null)
    try {
      await onSave(path, text)
      setDraft(null)
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : 'Could not save the change.')
    } finally {
      setSaving(false)
    }
  }

  function cancel() {
    setDraft(null)
    setError(null)
  }

  return (
    <li
      id={`field-${path}`}
      className={`rounded-md border transition-colors ${
        selected
          ? 'border-indigo-500 bg-indigo-50'
          : hasError
            ? 'border-red-200 bg-red-50/50'
            : 'border-transparent hover:bg-zinc-100'
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(path)}
        aria-pressed={selected}
        className="w-full px-3 py-2 text-left"
      >
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-xs font-medium text-zinc-500">{fieldLabel(path)}</span>
          <span className="flex flex-wrap justify-end gap-1">
            {issues.length > 0 && (
              <Badge tone={hasError ? 'danger' : 'warning'}>
                {issues.length} {issues.length === 1 ? 'issue' : 'issues'}
              </Badge>
            )}
            {agreement && <Badge tone={agreement.tone}>{agreement.label}</Badge>}
            {field.grounding === 'ungrounded' && <Badge tone="danger">Not found on page</Badge>}
            <Badge tone={field.source === 'human' ? 'info' : 'neutral'}>
              {SOURCE_LABEL[field.source]}
            </Badge>
            {field.source !== 'human' && <Badge>{Math.round(field.confidence * 100)}%</Badge>}
          </span>
        </div>
        <p className={`mt-0.5 break-words text-sm ${field.value ? '' : 'italic text-zinc-400'}`}>
          {field.value ?? 'Not found'}
        </p>
        {changedFromModel && (
          <p className="mt-0.5 break-words text-xs text-zinc-500">
            Model read: {field.original ?? 'nothing'}
          </p>
        )}
      </button>

      {selected && editable && (
        <div className="space-y-2 px-3 pb-3">
          {editing ? (
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault()
                const text = draft.trim()
                void save(text === '' ? null : text)
              }}
            >
              <label htmlFor={`edit-${path}`} className="sr-only">
                {fieldLabel(path)}
              </label>
              <input
                id={`edit-${path}`}
                autoFocus
                value={draft}
                disabled={saving}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') cancel()
                }}
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
              />
              <div className="flex flex-wrap gap-2">
                <Button type="submit" loading={saving}>
                  Save
                </Button>
                <Button variant="secondary" onClick={cancel} disabled={saving}>
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setDraft(field.value ?? '')}>
                {field.value ? 'Edit' : 'Enter value'}
              </Button>
              {changedFromModel && (
                <Button
                  variant="ghost"
                  loading={saving}
                  onClick={() => void save(field.original)}
                >
                  Restore model value
                </Button>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
        </div>
      )}
    </li>
  )
}
