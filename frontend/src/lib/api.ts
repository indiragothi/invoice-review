import { env } from './env.ts'
import type {
  AuthSession,
  BulkApproveResult,
  Client,
  CorrectionEmail,
  Decision,
  DocumentFilters,
  DocumentRecord,
  ExportFormat,
  HealthResponse,
  Ledger,
} from './types.ts'

/** A failed API call. `detail` is the server's reason, ready to show to the reviewer. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  /** The saved document when the upload failed after being stored (502 / 422). */
  readonly document: DocumentRecord | null

  constructor(status: number, detail: string, document: DocumentRecord | null = null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.document = document
  }

  /** The model provider was unavailable (retry later). */
  get isProviderBusy(): boolean {
    return this.status === 502
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** FastAPI sends `detail` as text, a list of validation errors, or a list of reasons. */
function detailText(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail !== '') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === 'string') return item
      if (isRecord(item) && typeof item.msg === 'string') return item.msg
      return ''
    })
    const text = parts.filter((part) => part !== '').join(' ')
    if (text !== '') return text
  }
  return fallback
}

async function errorFrom(response: Response): Promise<ApiError> {
  const fallback = `The server answered ${response.status}.`
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return new ApiError(response.status, fallback)
  }
  if (!isRecord(body)) return new ApiError(response.status, fallback)
  const document = isRecord(body.document) ? (body.document as unknown as DocumentRecord) : null
  return new ApiError(response.status, detailText(body.detail, fallback), document)
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, { credentials: 'include', ...init })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }
  if (!response.ok) throw await errorFrom(response)
  return response
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T
}

function jsonBody(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text === '' ? '' : `?${text}`
}

const docPath = (id: string) => `/api/documents/${encodeURIComponent(id)}`

export const api = {
  health: () => json<HealthResponse>('/health'),

  // Shared-password gate
  session: () => json<AuthSession>('/api/auth/session'),
  login: (password: string) =>
    json<AuthSession>('/api/auth/login', jsonBody('POST', { password })),
  logout: async () => {
    await send('/api/auth/logout', { method: 'POST' })
  },

  // Reference lists
  clients: () => json<Client[]>('/api/clients'),
  ledgers: () => json<Ledger[]>('/api/accounting/ledgers'),

  // Documents
  upload: (file: File, clientId: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('client_id', clientId)
    return json<DocumentRecord>('/api/documents', { method: 'POST', body: form })
  },
  listDocuments: (filters: DocumentFilters = {}) =>
    json<DocumentRecord[]>(`/api/documents${query({ ...filters })}`),
  getDocument: (id: string) => json<DocumentRecord>(docPath(id)),
  editFields: (id: string, fields: Record<string, string | null>) =>
    json<DocumentRecord>(docPath(id), jsonBody('PUT', { fields })),
  selectLedger: (id: string, ledgerCode: string) =>
    json<DocumentRecord>(`${docPath(id)}/ledger`, jsonBody('PUT', { ledger_code: ledgerCode })),
  decide: (id: string, decision: Decision) =>
    json<DocumentRecord>(`${docPath(id)}/decision`, jsonBody('POST', { decision })),
  bulkApprove: (ids: string[]) =>
    json<BulkApproveResult>('/api/documents/bulk-approve', jsonBody('POST', { ids })),
  retry: (id: string) => json<DocumentRecord>(`${docPath(id)}/retry`, { method: 'POST' }),
  correctionEmail: (id: string) =>
    json<CorrectionEmail>(`${docPath(id)}/correction-email`, { method: 'POST' }),
  deleteDocument: async (id: string) => {
    await send(docPath(id), { method: 'DELETE' })
  },

  // URLs for <img> / <a>; the session cookie goes along because the app and API share the site.
  pageImageUrl: (id: string, page: number) => `${env.apiBaseUrl}${docPath(id)}/pages/${page}`,
  fileUrl: (id: string) => `${env.apiBaseUrl}${docPath(id)}/file`,
  exportUrl: (format: ExportFormat, clientId?: string) =>
    `${env.apiBaseUrl}/api/export${query({ format, client_id: clientId })}`,
}
