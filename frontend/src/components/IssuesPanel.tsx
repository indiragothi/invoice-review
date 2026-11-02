import { useState } from 'react'

import { ApiError } from '../lib/api.ts'
import { fieldLabel } from '../lib/fields.ts'
import type { Issue } from '../lib/types.ts'
import { Badge } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

// The only issues whose `suggestion` is a replacement value (a GSTIN with one character fixed).
const GSTIN_CODES = new Set(['invalid_vendor_gstin', 'invalid_buyer_gstin'])

interface IssuesPanelProps {
  issues: Issue[]
  /** Paths that exist as fields, so an issue can jump to its field and box. */
  fieldPaths: ReadonlySet<string>
  editable: boolean
  onSelectField: (path: string) => void
  onApplySuggestion: (path: string, value: string) => Promise<void>
}

export function IssuesPanel({
  issues,
  fieldPaths,
  editable,
  onSelectField,
  onApplySuggestion,
}: IssuesPanelProps) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')

  async function apply(key: string, path: string, value: string) {
    setBusy(key)
    setError(null)
    try {
      await onApplySuggestion(path, value)
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : 'Could not apply the suggestion.')
    } finally {
      setBusy(null)
    }
  }

  function list(title: string, tone: 'danger' | 'warning', items: Issue[]) {
    if (items.length === 0) return null
    return (
      <div>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase text-zinc-500">
          {title} <Badge tone={tone}>{items.length}</Badge>
        </h3>
        <ul className="mt-2 space-y-2">
          {items.map((issue, index) => {
            const key = `${issue.code}-${index}`
            const path = issue.field
            const canJump = path !== null && fieldPaths.has(path)
            const canApply =
              editable &&
              path !== null &&
              fieldPaths.has(path) &&
              issue.suggestion !== null &&
              GSTIN_CODES.has(issue.code)
            return (
              <li
                key={key}
                className={`rounded-md border p-2.5 text-sm ${
                  tone === 'danger' ? 'border-red-200 bg-red-50/60' : 'border-amber-200 bg-amber-50/60'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-xs text-zinc-600">{issue.code}</code>
                  {path !== null &&
                    (canJump ? (
                      <button
                        type="button"
                        onClick={() => onSelectField(path)}
                        className="text-xs font-medium text-indigo-700 hover:underline"
                      >
                        {fieldLabel(path)}
                      </button>
                    ) : (
                      <span className="text-xs text-zinc-500">{fieldLabel(path)}</span>
                    ))}
                  {issue.supplier_fixable && <Badge tone="info">Supplier can fix</Badge>}
                </div>
                <p className="mt-1 text-zinc-800">{issue.message}</p>
                {canApply && path !== null && issue.suggestion !== null && (
                  <div className="mt-2 space-y-1">
                    <Button
                      variant="secondary"
                      loading={busy === key}
                      disabled={busy !== null}
                      onClick={() => void apply(key, path, issue.suggestion ?? '')}
                    >
                      Use {issue.suggestion}
                    </Button>
                    <p className="text-xs text-zinc-500">
                      A guess from the checksum. Compare with the page before using it.
                    </p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    )
  }

  return (
    <Card className="space-y-3">
      <h2 className="text-sm font-semibold">Issues</h2>
      {issues.length === 0 && (
        <p className="text-sm text-emerald-800">No issues. Every check passed.</p>
      )}
      {list('Errors (block approval)', 'danger', errors)}
      {list('Warnings', 'warning', warnings)}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
    </Card>
  )
}
