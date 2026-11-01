import { STATUS_LABEL } from '../lib/status.ts'
import type { DocumentStatus } from '../lib/types.ts'
import { Badge } from './ui/Badge.tsx'
import type { Tone } from './ui/Badge.tsx'

const STATUS_TONE: Record<DocumentStatus, Tone> = {
  processing: 'info',
  ready: 'success',
  needs_review: 'warning',
  approved: 'success',
  rejected: 'neutral',
  failed: 'danger',
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>
}
