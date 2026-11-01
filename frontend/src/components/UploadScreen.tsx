import { useEffect, useRef, useState } from 'react'

import { api } from '../lib/api.ts'
import { ACCEPT, fileProblem, formatSize } from '../lib/files.ts'
import type { Client } from '../lib/types.ts'
import { FilePreview } from './FilePreview.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

type ClientsState =
  | { kind: 'loading' }
  | { kind: 'ready'; clients: Client[] }
  | { kind: 'error'; message: string }

interface UploadScreenProps {
  onSubmit: (file: File, client: Client) => void
  onBack: () => void
}

export function UploadScreen({ onSubmit, onBack }: UploadScreenProps) {
  const [clients, setClients] = useState<ClientsState>({ kind: 'loading' })
  const [clientId, setClientId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    api
      .clients()
      .then((list) => {
        if (!cancelled) setClients({ kind: 'ready', clients: list })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Unknown error'
          setClients({ kind: 'error', message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  function choose(chosen: File | undefined) {
    if (!chosen) return
    const found = fileProblem(chosen)
    setProblem(found)
    setFile(found === null ? chosen : null)
  }

  const client =
    clients.kind === 'ready' ? clients.clients.find((c) => c.id === clientId) : undefined
  const canSubmit = file !== null && client !== undefined

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Upload a document</h1>

      <Card className="space-y-2">
        <label htmlFor="client" className="block text-sm font-medium">
          Client
        </label>
        {clients.kind === 'loading' && <p className="text-sm text-zinc-500">Loading clients…</p>}
        {clients.kind === 'error' && (
          <p role="alert" className="text-sm text-red-700">
            Could not load the clients: {clients.message}
          </p>
        )}
        {clients.kind === 'ready' && (
          <>
            <select
              id="client"
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">Select a client…</option>
              {clients.clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · {c.city}
                </option>
              ))}
            </select>
            {client && (
              <p className="text-xs text-zinc-500">
                GSTIN <code>{client.gstin}</code>. The buyer on a purchase invoice must match it.
              </p>
            )}
          </>
        )}
      </Card>

      <Card className="space-y-3">
        <p className="text-sm font-medium">File</p>
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            choose(event.dataTransfer.files[0])
          }}
          className={`flex flex-col items-center gap-2 rounded-md border-2 border-dashed p-6 text-sm ${
            dragging ? 'border-indigo-500 bg-indigo-50' : 'border-zinc-300'
          }`}
        >
          <p className="text-zinc-600">Drop a PDF, PNG or JPG here, or</p>
          <Button variant="secondary" onClick={() => input.current?.click()}>
            Choose a file
          </Button>
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(event) => {
              choose(event.target.files?.[0])
              event.target.value = ''
            }}
          />
        </div>
        {problem && (
          <p role="alert" className="text-sm text-red-700">
            {problem}
          </p>
        )}
        {file && (
          <>
            <p className="text-sm text-zinc-600">
              {file.name} · {formatSize(file.size)}
            </p>
            <FilePreview file={file} />
          </>
        )}
      </Card>

      <div className="flex gap-2">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button
          disabled={!canSubmit}
          onClick={() => {
            if (file && client) onSubmit(file, client)
          }}
        >
          Upload and review
        </Button>
      </div>
    </div>
  )
}
