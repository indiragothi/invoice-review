// API shapes (docs/api-and-pipeline.md). Components use these, never raw JSON.

export interface HealthResponse {
  status: 'ok'
  llm_provider: 'gemini' | 'nvidia'
  model: string
}

export interface AuthSession {
  gate_enabled: boolean
  authenticated: boolean
}

export interface Client {
  id: string
  name: string
  gstin: string
  state_code: string
  city: string
}

export interface Ledger {
  code: string
  name: string
  typical: string
}

export type DocumentStatus =
  | 'processing'
  | 'ready'
  | 'needs_review'
  | 'approved'
  | 'rejected'
  | 'failed'

export type DocumentType = 'invoice' | 'receipt'
export type Severity = 'error' | 'warning'
export type Grounding = 'grounded' | 'ungrounded' | 'missing'
export type FieldSource = 'pdf_text' | 'ocr' | 'reading_b' | 'human'
export type Agreement = 'agree' | 'differ' | 'missing' | 'filled'

/** [x0, y0, x1, y1] in the pixel space of the rendered page image. */
export type Box = [number, number, number, number]

export interface Issue {
  code: string
  severity: Severity
  field: string | null
  message: string
  suggestion: string | null
  supplier_fixable: boolean
}

export interface FieldEvidence {
  page: number | null
  word_ids: string[]
  box: Box | null
}

export interface ReviewField {
  value: string | null
  original: string | null
  source: FieldSource
  confidence: number
  grounding: Grounding
  agreement: Agreement | null
  evidence: FieldEvidence
}

export interface ReviewData {
  fields: Record<string, ReviewField>
}

export interface LedgerState {
  suggested_code: string | null
  reason: string
  selected_code: string | null
  overridden: boolean
}

export interface DocumentReview {
  mode: string
  ran: boolean
  why: string | null
  filled: string[]
  agreement: Record<string, Agreement>
}

export interface DocumentRecord {
  id: string
  client_id: string
  original_filename: string
  content_type: string
  page_count: number
  status: DocumentStatus
  document_type: DocumentType | null
  classification: { document_type: DocumentType; reason: string } | null
  review_data: ReviewData | null
  document_review: DocumentReview | null
  issues: Issue[]
  ledger: LedgerState | null
  history: Record<string, unknown>[]
  pipeline_run: Record<string, unknown> | null
  error_message: string | null
  supplier_action_required: boolean
  created_at: string
  updated_at: string
}

export interface DocumentFilters {
  status?: DocumentStatus
  client_id?: string
}

export interface SkippedDocument {
  id: string
  reason: string
}

export interface BulkApproveResult {
  approved: DocumentRecord[]
  skipped: SkippedDocument[]
}

export interface CorrectionEmail {
  subject: string
  body: string
  issue_codes: string[]
}

export type Decision = 'approved' | 'rejected'
export type ExportFormat = 'csv' | 'xlsx'
