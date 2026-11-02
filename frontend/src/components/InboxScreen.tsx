import { useEffect, useState } from 'react'

import { ApiError, api } from '../lib/api.ts'
import { formatDateTime } from '../lib/format.ts'
import { STATUS_LABEL } from '../lib/status.ts'
import type { Client, DocumentFilters, DocumentRecord, DocumentStatus } from '../lib/types.ts'
import { StatusBadge } from './StatusBadge.tsx'
import { Badge } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'
import { ConfirmDialog } from './ui/ConfirmDialog.tsx'

const STATUSES = Object.keys(STATUS_LABEL) as DocumentStatus[]

interface BulkSummary {
  approved: string[]
  skipped: { name: string; reason: string }[]
}

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
  const [selection, setSelection] = useState<ReadonlySet<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const [approving, setApproving] = useState(false)
  const [bulkError, setBulkError] = useState<string | null>(null)
  const [summary, setSummary] = useState<BulkSummary | null>(null)

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

  // Only `ready` documents can be approved in bulk; other rows have no checkbox.
  const documents = !loading && loaded.kind === 'ok' ? loaded.documents : []
  const readyDocs = documents.filter((doc) => doc.status === 'ready')
  const chosen = readyDocs.filter((doc) => selection.has(doc.id))
  const allChosen = readyDocs.length > 0 && chosen.length === readyDocs.length

  function toggle(id: string) {
    const next = new Set(selection)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelection(next)
  }

  function toggleAll() {
    setSelection(allChosen ? new Set() : new Set(readyDocs.map((doc) => doc.id)))
  }

  async function approveChosen() {
    setApproving(true)
    setBulkError(null)
    const names = new Map(documents.map((doc) => [doc.id, doc.original_filename]))
    try {
      const result = await api.bulkApprove(chosen.map((doc) => doc.id))
      setSummary({
        approved: result.approved.map((doc) => doc.original_filename),
        skipped: result.skipped.map((item) => ({
          name: names.get(item.id) ?? item.id,
          reason: item.reason,
        })),
      })
      setSelection(new Set())
      setReload((n) => n + 1)
    } catch (failure) {
      setBulkError(failure instanceof ApiError ? failure.detail : messageOf(failure))
    } finally {
      setApproving(false)
      setConfirming(false)
    }
  }

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

      {summary && (
        <div role="status" className="space-y-1 rounded-lg border border-zinc-200 bg-white p-3 text-sm">
          <p className="font-medium text-emerald-800">
            Approved {summary.approved.length}
            {summary.approved.length > 0 && `: ${summary.approved.join(', ')}`}
          </p>
          {summary.skipped.length > 0 && (
            <div>
              <p className="font-medium text-amber-800">Skipped {summary.skipped.length}</p>
              <ul className="list-disc pl-5 text-zinc-700">
                {summary.skipped.map((item, index) => (
                  <li key={`${item.name}-${index}`}>
                    {item.name}: {item.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <Button variant="ghost" onClick={() => setSummary(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {bulkError && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          Bulk approve failed: {bulkError}
        </p>
      )}

      {chosen.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm">
          <span>{chosen.length} selected</span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setSelection(new Set())}>
              Clear
            </Button>
            <Button onClick={() => setConfirming(true)}>Approve {chosen.length} selected</Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        title={`Approve ${chosen.length} documents?`}
        confirmLabel="Approve"
        busy={approving}
        onConfirm={() => void approveChosen()}
        onCancel={() => setConfirming(false)}
      >
        They will be locked and included in the export. A document without a selected ledger is
        skipped, and you will see why.
      </ConfirmDialog>

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
                <th className="w-8 px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label="Select all ready documents"
                    checked={allChosen}
                    disabled={readyDocs.length === 0}
                    onChange={toggleAll}
                  />
                </th>
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
                      {doc.status === 'ready' && (
                        <input
                          type="checkbox"
                          aria-label={`Select ${doc.original_filename}`}
                          checked={selection.has(doc.id)}
                          onChange={() => toggle(doc.id)}
                        />
                      )}
                    </td>
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
