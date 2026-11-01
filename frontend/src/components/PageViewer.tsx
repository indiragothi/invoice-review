import { useState } from 'react'

import { api } from '../lib/api.ts'
import { fieldLabel } from '../lib/fields.ts'
import type { ReviewData } from '../lib/types.ts'

interface PageViewerProps {
  documentId: string
  pageCount: number
  page: number
  onPageChange: (page: number) => void
  data: ReviewData
  selected: string | null
  /** Paths that have an open issue; their boxes are drawn in red. */
  flagged: ReadonlySet<string>
  onSelect: (path: string) => void
}

interface Size {
  url: string
  width: number
  height: number
}

/** The rendered page with one box per field. Boxes are in the pixel space of the page image, so
 * they are placed in percent of its natural size and scale with whatever size is displayed. */
export function PageViewer({
  documentId,
  pageCount,
  page,
  onPageChange,
  data,
  selected,
  flagged,
  onSelect,
}: PageViewerProps) {
  const url = api.pageImageUrl(documentId, page)
  const [size, setSize] = useState<Size | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  // `size` belongs to one image url; for another page it is ignored until that image loads.
  const natural = size !== null && size.url === url ? size : null

  const boxes = Object.entries(data.fields).flatMap(([path, field]) => {
    const { box, page: boxPage } = field.evidence
    return box !== null && boxPage === page ? [{ path, box }] : []
  })
  // Draw the selected box last so it sits on top.
  boxes.sort((a, b) => Number(a.path === selected) - Number(b.path === selected))

  return (
    <div className="space-y-2">
      {pageCount > 1 && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-zinc-500">Page</span>
          {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => onPageChange(n)}
              aria-current={n === page}
              className={`rounded-md px-2.5 py-1 ${
                n === page ? 'bg-indigo-600 text-white' : 'bg-white ring-1 ring-zinc-300'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      )}
      {failed === url ? (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          The page image could not be loaded.
        </p>
      ) : (
        <div className="relative overflow-hidden rounded-md border border-zinc-200 bg-white">
          <img
            src={url}
            alt={`Page ${page}`}
            className="block w-full"
            onLoad={(event) =>
              setSize({
                url,
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              })
            }
            onError={() => setFailed(url)}
          />
          {natural &&
            boxes.map(({ path, box }) => {
              const isSelected = path === selected
              const tone = isSelected
                ? 'border-indigo-600 bg-indigo-500/25 z-10'
                : flagged.has(path)
                  ? 'border-red-500 bg-red-500/10 hover:bg-red-500/20'
                  : 'border-amber-500/70 bg-amber-300/10 hover:bg-amber-300/30'
              return (
                <button
                  key={path}
                  type="button"
                  title={fieldLabel(path)}
                  aria-label={fieldLabel(path)}
                  aria-pressed={isSelected}
                  onClick={() => onSelect(path)}
                  className={`absolute border-2 ${tone}`}
                  style={{
                    left: `${(box[0] / natural.width) * 100}%`,
                    top: `${(box[1] / natural.height) * 100}%`,
                    width: `${((box[2] - box[0]) / natural.width) * 100}%`,
                    height: `${((box[3] - box[1]) / natural.height) * 100}%`,
                  }}
                />
              )
            })}
        </div>
      )}
    </div>
  )
}
