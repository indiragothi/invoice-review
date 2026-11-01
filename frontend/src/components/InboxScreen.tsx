import { useEffect, useState } from 'react'

import { api } from '../lib/api.ts'
import { formatDateTime } from '../lib/format.ts'
import type { Client, DocumentFilters, DocumentRecord, DocumentStatus } from '../lib/types.ts'
import { STATUS_LABEL } from '../lib/status.ts'
import { StatusBadge } from './StatusBadge.tsx'
import { Badge } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

const STATUSES = Object.keys(STATUS_LABEL) as DocumentStatus[]

type Loaded =
  | { key: string; kind: 'ok'; documents: DocumentRecord[] }
  | { key: string; kind: 'error'; message: string }

interface InboxScreenProps {
  onOpen: (document: DocumentRecord) => void
  onUpload: () => void
  onHome: () => void
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown error'
}

export function InboxScreen({ onOpen, onUpload, onHome }: InboxScreenProps) {
  const [status, setStatus] = useState<DocumentStatus | ''>('')
  const [clientId, setClientId] = useState('')
  const [clients, setClients] = useState<Client[]>([])
  // Bumped by "Refresh"; part of the key so the same filters load again.
  const [reload, setReload] = useState(0)
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  const key = `${status}|${clientId}|${reload}`

  useEffect(() => {
    let cancelled = false
    api
      .clients()
      .then((list) => {
        if (!cancelled) setClients(list)
      })
      .catch(() => {
        // The filter still works by id; the list screen shows its own error if the API is down.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const filters: DocumentFilters = {}
    if (status !== '') filters.status = status
    if (clientId !== '') filters.client_id = clientId
    api
      .listDocuments(filters)
      .then((documents) => {
        if (!cancelled) setLoaded({ key, kind: 'ok', documents })
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoaded({ key, kind: 'error', message: messageOf(error) })
      })
    return () => {
      cancelled = true
    }
  }, [key, status, clientId])

  const loading = loaded === null || loaded.key !== key
  const clientName = (id: string) => clients.find((c) => c.id === id)?.name ?? id

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onHome}>
            Home
          </Button>
          <Button onClick={onUpload}>Upload a document</Button>
        </div>
      </div>

      <Card className="flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor="status-filter" className="block text-xs font-medium text-zinc-600">
            Status
          </label>
          <select
            id="status-filter"
            value={status}
            onChange={(event) => setStatus(event.target.value as DocumentStatus | '')}
            className="mt-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="client-filter" className="block text-xs font-medium text-zinc-600">
            Client
          </label>
          <select
            id="client-filter"
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
            className="mt-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All clients</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
          Refresh
        </Button>
      </Card>

      {loading && <p className="text-sm text-zinc-500">Loading documents…</p>}

      {!loading && loaded.kind === 'error' && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
          <p className="font-medium text-red-800">Could not load the documents</p>
          <p className="mt-1 text-red-700">{loaded.message}</p>
        </div>
      )}

      {!loading && loaded.kind === 'ok' && loaded.documents.length === 0 && (
        <Card className="text-sm text-zinc-600">
          {status === '' && clientId === ''
            ? 'No documents yet. Upload one to start.'
            : 'No documents match these filters.'}
        </Card>
      )}

      {!loading && loaded.kind === 'ok' && loaded.documents.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-3 py-2 font-medium">Document</th>
                <th className="px-3 py-2 font-medium">Client</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Issues</th>
                <th className="px-3 py-2 font-medium">Uploaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {loaded.documents.map((doc) => {
                const errors = doc.issues.filter((i) => i.severity === 'error').length
                const warnings = doc.issues.length - errors
                return (
                  <tr key={doc.id} className="hover:bg-zinc-50">
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => onOpen(doc)}
                        className="text-left font-medium text-indigo-700 hover:underline"
                      >
                        {doc.original_filename}
                      </button>
                    </td>
                    <td className="px-3 py-2">{clientName(doc.client_id)}</td>
                    <td className="px-3 py-2 capitalize">{doc.document_type ?? '–'}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="space-x-1 px-3 py-2">
                      {errors > 0 && <Badge tone="danger">{errors} errors</Badge>}
                      {warnings > 0 && <Badge tone="warning">{warnings} warnings</Badge>}
                      {doc.issues.length === 0 && <span className="text-zinc-400">–</span>}
                    </td>
                    <td className="px-3 py-2 text-zinc-600">{formatDateTime(doc.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
