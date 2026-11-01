import type { DocumentStatus } from './types.ts'

export const STATUS_LABEL: Record<DocumentStatus, string> = {
  processing: 'Processing',
  ready: 'Ready',
  needs_review: 'Needs review',
  approved: 'Approved',
  rejected: 'Rejected',
  failed: 'Failed',
}
