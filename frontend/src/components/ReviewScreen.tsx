import { useEffect, useMemo, useState } from 'react'

import { api } from '../lib/api.ts'
import { groupFields } from '../lib/fields.ts'
import type { Client, DocumentRecord, Issue } from '../lib/types.ts'
import { FieldRow } from './FieldRow.tsx'
import { PageViewer } from './PageViewer.tsx'
import { StatusBadge } from './StatusBadge.tsx'
import { Badge } from './ui/Badge.tsx'
import { Button } from './ui/Button.tsx'
import { Card } from './ui/Card.tsx'

interface ReviewScreenProps {
  record: DocumentRecord
  onInbox: () => void
  onUpload: () => void
}

export function ReviewScreen({ record, onInbox, onUpload }: ReviewScreenProps) {
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const [client, setClient] = useState<Client | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    api
      .clients()
      .then((list) => {
        if (!cancelled) setClient(list.find((c) => c.id === record.client_id))
      })
      .catch(() => {
        // The client id is shown instead of the name.
      })
    return () => {
      cancelled = true
    }
  }, [record.client_id])

  const data = record.review_data
  const groups = useMemo(() => (data ? groupFields(data) : null), [data])

  // Issues by the field they point at.
  const issuesByField = useMemo(() => {
    const map = new Map<string, Issue[]>()
    for (const issue of record.issues) {
      if (issue.field === null) continue
      map.set(issue.field, [...(map.get(issue.field) ?? []), issue])
    }
    return map
  }, [record.issues])
  const flagged = useMemo(() => new Set(issuesByField.keys()), [issuesByField])

  function select(path: string) {
    setSelected(path)
    const boxPage = data?.fields[path]?.evidence.page
    if (boxPage) setPage(boxPage)
    // The row exists already; bring it into view when the click came from a box.
    document.getElementById(`field-${path}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  function rows(paths: string[]) {
    if (data === null) return null
    return paths.map((path) => {
      const field = data.fields[path]
      if (field === undefined) return null
      return (
        <FieldRow
          key={path}
          path={path}
          field={field}
          selected={selected === path}
          issues={issuesByField.get(path) ?? []}
          onSelect={select}
        />
      )
    })
  }

  const errors = record.issues.filter((i) => i.severity === 'error').length
  const warnings = record.issues.length - errors

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {record.original_filename}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-zinc-600">
            <StatusBadge status={record.status} />
            {record.document_type && <Badge>{record.document_type}</Badge>}
            <span>{client?.name ?? record.client_id}</span>
            {errors > 0 && <Badge tone="danger">{errors} errors</Badge>}
            {warnings > 0 && <Badge tone="warning">{warnings} warnings</Badge>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onInbox}>
            Back to inbox
          </Button>
          <Button onClick={onUpload}>Upload another</Button>
        </div>
      </div>

      {record.status === 'failed' || data === null || groups === null ? (
        <Card role="alert" className="text-sm">
          <p className="font-medium text-red-800">This document has no extracted fields.</p>
          {record.error_message && <p className="mt-1 text-zinc-700">{record.error_message}</p>}
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="lg:sticky lg:top-4 lg:self-start">
            <PageViewer
              documentId={record.id}
              pageCount={record.page_count}
              page={page}
              onPageChange={setPage}
              data={data}
              selected={selected}
              flagged={flagged}
              onSelect={select}
            />
          </div>

          <div className="space-y-4">
            <Card className="space-y-1 p-2">
              <h2 className="px-3 pt-1 text-sm font-semibold">Fields</h2>
              <ul className="space-y-0.5">
                {rows(groups.header)}
              </ul>
            </Card>

            {groups.lineItems.length > 0 && (
              <Card className="space-y-3 p-2">
                <h2 className="px-3 pt-1 text-sm font-semibold">Line items</h2>
                {groups.lineItems.map((item) => (
                  <div key={item.index}>
                    <p className="px-3 text-xs font-medium uppercase text-zinc-400">
                      Item {item.index + 1}
                    </p>
                    <ul className="space-y-0.5">
                      {rows(item.paths)}
                    </ul>
                  </div>
                ))}
              </Card>
            )}

            {groups.taxLines.length > 0 && (
              <Card className="space-y-3 p-2">
                <h2 className="px-3 pt-1 text-sm font-semibold">Tax lines</h2>
                {groups.taxLines.map((tax) => (
                  <div key={tax.index}>
                    <p className="px-3 text-xs font-medium uppercase text-zinc-400">
                      Tax {tax.index + 1}
                    </p>
                    <ul className="space-y-0.5">
                      {rows(tax.paths)}
                    </ul>
                  </div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
