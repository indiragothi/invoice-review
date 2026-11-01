import { fieldLabel } from '../lib/fields.ts'
import type { Agreement, FieldSource, Issue, ReviewField } from '../lib/types.ts'
import { Badge } from './ui/Badge.tsx'
import type { Tone } from './ui/Badge.tsx'

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
  onSelect: (path: string) => void
}

export function FieldRow({ path, field, selected, issues, onSelect }: FieldRowProps) {
  const hasError = issues.some((issue) => issue.severity === 'error')
  const agreement = field.agreement ? AGREEMENT[field.agreement] : null

  return (
    <li id={`field-${path}`}>
      <button
        type="button"
        onClick={() => onSelect(path)}
        aria-pressed={selected}
        className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
          selected
            ? 'border-indigo-500 bg-indigo-50'
            : hasError
              ? 'border-red-200 bg-red-50/50 hover:bg-red-50'
              : 'border-transparent hover:bg-zinc-100'
        }`}
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
            {field.source !== 'human' && (
              <Badge>{Math.round(field.confidence * 100)}%</Badge>
            )}
          </span>
        </div>
        <p className={`mt-0.5 break-words text-sm ${field.value ? '' : 'italic text-zinc-400'}`}>
          {field.value ?? 'Not found'}
        </p>
      </button>
    </li>
  )
}
