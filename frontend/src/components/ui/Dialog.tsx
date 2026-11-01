import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

interface DialogProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  /** Buttons shown at the bottom. */
  footer?: ReactNode
}

/** Modal built on the native <dialog>: focus trap, Esc to close and backdrop come for free. */
export function Dialog({ open, title, onClose, children, footer }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose()
      }}
      aria-labelledby="dialog-title"
      className="m-auto w-full max-w-lg rounded-lg p-0 shadow-xl backdrop:bg-zinc-900/40"
    >
      <div className="p-5">
        <h2 id="dialog-title" className="text-lg font-semibold">
          {title}
        </h2>
        <div className="mt-3 text-sm text-zinc-700">{children}</div>
      </div>
      {footer && (
        <div className="flex justify-end gap-2 border-t border-zinc-200 bg-zinc-50 px-5 py-3">
          {footer}
        </div>
      )}
    </dialog>
  )
}
